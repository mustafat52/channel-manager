import re
from app.utils import date_utils


class VrboParsingError(Exception):
    pass


def _extract_with_regex(pattern: str, text: str, field_name: str):
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise VrboParsingError(f"{field_name} not found in Vrbo email.")
    return match.group(1).strip()


def _normalize_date(date_str: str) -> str:
    try:
        parsed_date = date_utils.parse(date_str, fuzzy=True)
        return parsed_date.date().isoformat()
    except Exception:
        raise VrboParsingError(f"Invalid date format: {date_str}")


def _extract_guest_name(email_text: str) -> str:
    """
    Extract guest name from 'Traveler Name' section.
    """
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "Traveler Name" in line:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                return lines[j].strip().title()

    raise VrboParsingError("Traveler Name not found in Vrbo email.")


def parse_vrbo(email_text: str) -> dict:
    """
    Parses Vrbo confirmation email text
    and returns normalized booking dictionary.
    """

    # Reservation ID
    booking_id = _extract_with_regex(
        r"Reservation ID\s*\n\s*([A-Z0-9\-]+)",
        email_text,
        "Reservation ID",
    )

    # Property ID
    property_id = _extract_with_regex(
        r"Property\s*#(\d+)",
        email_text,
        "Property ID",
    )

    # Guest Name
    guest_name = _extract_guest_name(email_text)

    # --- Date Extraction ---
    # Format 1: confirmation sentence
    date_match = re.search(
        r"reservation from (.*?) to (.*?)\.",
        email_text,
        re.IGNORECASE,
    )

    if date_match:
        check_in_raw = date_match.group(1).strip()
        check_out_raw = date_match.group(2).strip()

    else:
        # Format 2: Dates block
        dates_block = re.search(
            r"Dates\s*\n\s*(.*?)\n",
            email_text,
            re.IGNORECASE,
        )

        if not dates_block:
            raise VrboParsingError("Reservation dates not found in Vrbo email.")

        dates_line = dates_block.group(1).strip()
        # Example: "Feb 21 - Mar 24, 2026, 31 nights"

        date_range = dates_line.split(",")[0]
        parts = date_range.split(" - ")

        if len(parts) != 2:
            raise VrboParsingError("Invalid date range format in Vrbo email.")

        check_in_raw, check_out_raw = parts

    check_in = _normalize_date(check_in_raw)
    check_out = _normalize_date(check_out_raw)

    return {
        "platform": "vrbo",
        "booking_id": booking_id,
        "platform_property_id": property_id,
        "guest_name": guest_name,
        "check_in": check_in,
        "check_out": check_out,
    }