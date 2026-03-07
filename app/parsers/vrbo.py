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
    Extract property ID from Vrbo email.
    Handles multiple formats including forwarded emails.
    """

    # Case 1: Property #4989700
    match = re.search(r"property\s*#\s*(\d+)", email_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Case 2: Property on one line, ID on next line
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "property" in line.lower():

            # look ahead for number
            for j in range(i+1, min(i+4, len(lines))):
                candidate = lines[j].strip()

                match = re.search(r"#\s*(\d+)", candidate)
                if match:
                    return match.group(1)

    raise VrboParsingError("Property ID not found in Vrbo email.")

def _extract_dates(email_text: str):

    # Case 1: "Reservation from Tom Grace: Feb 21 - Mar 24, 2026"
    match = re.search(
        r"([A-Za-z]{3,9}\s\d{1,2})\s*-\s*([A-Za-z]{3,9}\s\d{1,2},\s\d{4})",
        email_text
    )

    if match:
        check_in_raw = match.group(1)
        check_out_raw = match.group(2)

        # If checkin has no year, append the year from checkout
        if "," not in check_in_raw:
            year = check_out_raw.split(",")[1].strip()
            check_in_raw = f"{check_in_raw}, {year}"

        check_in = _normalize_date(check_in_raw)
        check_out = _normalize_date(check_out_raw)

        return check_in, check_out


    # Case 2: Dates block
    block_match = re.search(
        r"Dates\s*\n\s*(.*?)\n",
        email_text,
        re.IGNORECASE,
    )

    if block_match:

        dates_line = block_match.group(1)

        date_range = dates_line.split(",")[0]

        parts = date_range.split(" - ")

        if len(parts) != 2:
            raise VrboParsingError("Invalid Vrbo date range.")

        check_in_raw, check_out_raw = parts

        check_in = _normalize_date(check_in_raw)
        check_out = _normalize_date(check_out_raw)

        return check_in, check_out


    raise VrboParsingError("Reservation dates not found.")

def _extract_guest_name(email_text: str) -> str:
    """
    Extract traveler name from Vrbo email.
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