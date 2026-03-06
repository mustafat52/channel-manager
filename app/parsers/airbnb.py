import re
from app.utils import date_utils


class AirbnbParsingError(Exception):
    pass


def _extract_with_regex(pattern: str, text: str, field_name: str):
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise AirbnbParsingError(f"{field_name} not found in Airbnb email.")
    return match.group(1).strip()


def _normalize_date(date_str: str) -> str:
    try:
        parsed_date = date_utils.parse(date_str, fuzzy=True)
        return parsed_date.date().isoformat()
    except Exception:
        raise AirbnbParsingError(f"Invalid date format: {date_str}")


def _clean_property_name(name: str) -> str:
    """
    Clean Airbnb promotional text and links.
    """

    name = name.strip()

    # Remove HTML links
    name = re.sub(r"<.*?>", "", name)

    # Remove promotional suffix
    if " l " in name:
        name = name.split(" l ")[0].strip()

    # Remove trailing punctuation
    name = name.rstrip("!").strip()

    return name


def _extract_guest_name(email_text: str) -> str:
    """
    Extract guest name by locating 'Identity verified'
    and skipping URL lines above it.
    """

    lines = email_text.splitlines()

    for i, line in enumerate(lines):

        if "Identity verified" in line or "reviews" in line:

            j = i - 1

            while j >= 0:

                candidate = lines[j].strip()

                # skip empty lines
                if not candidate:
                    j -= 1
                    continue

                # skip links
                if candidate.startswith("<http") or "airbnb.com" in candidate:
                    j -= 1
                    continue

                return candidate

    raise AirbnbParsingError("Guest Name not found in Airbnb email.")

def parse_airbnb(email_text: str) -> dict:
    """
    Parse Airbnb confirmation email.
    """

    booking_id = _extract_with_regex(
        r"Confirmation code\s*\n+\s*([A-Z0-9]+)",
        email_text,
        "Booking ID",
    )

    guest_name = _extract_guest_name(email_text)

    # PROPERTY NAME FIX
    property_name = _extract_with_regex(
        r"\n\s*([^\n]+)\s*\n(?:https?:\/\/[^\n]+\n)?\s*Entire",
        email_text,
        "Property Name",
    )

    property_name = _clean_property_name(property_name)

    check_in_raw = _extract_with_regex(
        r"Check-in\s*\n+\s*([^\n]+)",
        email_text,
        "Check-in Date",
    )

    check_out_raw = _extract_with_regex(
        r"Checkout\s*\n+\s*([^\n]+)",
        email_text,
        "Check-out Date",
    )

    check_in = _normalize_date(check_in_raw)
    check_out = _normalize_date(check_out_raw)

    return {
        "platform": "airbnb",
        "booking_id": booking_id,
        "property_name": property_name,
        "guest_name": guest_name,
        "check_in": check_in,
        "check_out": check_out,
    }


def parse_airbnb_cancellation(email_text: str) -> dict:

    match = re.search(
        r"Reservation\s+([A-Z0-9]+)",
        email_text
    )

    if not match:
        raise AirbnbParsingError("Booking ID not found in cancellation email.")

    booking_id = match.group(1).strip()

    return {
        "platform": "airbnb",
        "booking_id": booking_id,
        "status": "cancelled",
    }