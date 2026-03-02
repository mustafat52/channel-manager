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
    Removes Airbnb promotional suffixes like:
    ' l W/ 30 Days Deals!'
    """
    name = name.strip()

    # Remove promotional suffix after ' l '
    if " l " in name:
        name = name.split(" l ")[0].strip()

    # Remove trailing punctuation
    name = name.rstrip("!").strip()

    return name


def _extract_guest_name(email_text: str) -> str:
    """
    Extract guest name by locating 'Identity verified'
    and taking nearest non-empty line above it.
    """
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "Identity verified" in line:
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1

            if j >= 0:
                return lines[j].strip()

    raise AirbnbParsingError("Guest Name not found in Airbnb email.")


def parse_airbnb(email_text: str) -> dict:
    """
    Parses Airbnb confirmation email text
    and returns normalized booking dictionary.
    """

    # Booking ID
    booking_id = _extract_with_regex(
        r"Confirmation code\s*\n+\s*([A-Z0-9]+)",
        email_text,
        "Booking ID",
    )

    # Guest Name
    guest_name = _extract_guest_name(email_text)

    # Property Name
    property_name = _extract_with_regex(
        r"\n\s*(.*?)\s*\n\s*Entire home/apt",
        email_text,
        "Property Name",
    )

    property_name = _clean_property_name(property_name)

    # Check-in
    check_in_raw = _extract_with_regex(
        r"Check-in\s*\n+\s*(.*?)\n",
        email_text,
        "Check-in Date",
    )

    # Check-out
    check_out_raw = _extract_with_regex(
        r"Checkout\s*\n+\s*(.*?)\n",
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