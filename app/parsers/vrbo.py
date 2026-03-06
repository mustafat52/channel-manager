import re
from app.utils import date_utils


class VrboParsingError(Exception):
    pass


def _normalize_date(date_str: str) -> str:
    try:
        parsed_date = date_utils.parse(date_str, fuzzy=True)
        return parsed_date.date().isoformat()
    except Exception:
        raise VrboParsingError(f"Invalid date format: {date_str}")


def _extract_booking_id(email_text: str) -> str:
    """
    Extract booking ID from 'Reservation ID' section.
    """

    lines = email_text.splitlines()

    for i, line in enumerate(lines):

        if "reservation id" in line.lower():

            j = i + 1

            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                return lines[j].strip()

    raise VrboParsingError("Reservation ID not found in Vrbo email.")

def _extract_property_id(email_text: str) -> str:
    """
    Extract property id from email.
    Works for both formats:
    Property
    #4034088

    or

    Property    #4034088
    """

    match = re.search(r"Property\s*#(\d+)", email_text, re.IGNORECASE)

    if match:
        return match.group(1)

    raise VrboParsingError("Property ID not found in Vrbo email.")

def _extract_guest_name(email_text: str) -> str:
    """
    Extract guest name from 'Traveler Name' section.
    """

    lines = email_text.splitlines()

    for i, line in enumerate(lines):

        if "traveler name" in line.lower():

            j = i + 1

            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):

                name = lines[j].strip()

                return name.title()

    raise VrboParsingError("Traveler Name not found in Vrbo email.")


def _extract_dates(email_text: str):

    # Format 1: sentence confirmation
    sentence_match = re.search(
        r"reservation from (.*?) to (.*?)\.",
        email_text,
        re.IGNORECASE,
    )

    if sentence_match:

        check_in_raw = sentence_match.group(1)
        check_out_raw = sentence_match.group(2)

    else:

        # Format 2: dates block
        block_match = re.search(
            r"Dates\s*\n\s*(.*?)\n",
            email_text,
            re.IGNORECASE,
        )

        if not block_match:
            raise VrboParsingError("Reservation dates not found.")

        dates_line = block_match.group(1)

        # Example: Apr 9 - Apr 12, 2026, 3 nights
        date_range = dates_line.split(",")[0]

        parts = date_range.split(" - ")

        if len(parts) != 2:
            raise VrboParsingError("Invalid Vrbo date range.")

        check_in_raw, check_out_raw = parts

    check_in = _normalize_date(check_in_raw)
    check_out = _normalize_date(check_out_raw)

    return check_in, check_out


def parse_vrbo(email_text: str) -> dict:
    """
    Parse Vrbo booking confirmation email.
    """

    if "reservation id" not in email_text.lower():
        raise VrboParsingError("Not a Vrbo reservation email.")

    booking_id = _extract_booking_id(email_text)

    property_id = _extract_property_id(email_text)

    guest_name = _extract_guest_name(email_text)

    check_in, check_out = _extract_dates(email_text)

    return {
        "platform": "vrbo",
        "booking_id": booking_id,
        "platform_property_id": property_id,
        "guest_name": guest_name,
        "check_in": check_in,
        "check_out": check_out,
    }