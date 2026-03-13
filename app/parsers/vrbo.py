import re
import logging

from datetime import date
from app.parsers.utils import (
    normalize_email_text,
    check_email_size,
    normalize_date,
    validate_date_range,
    cap_field,
    MAX_BOOKING_ID_LEN,
    MAX_GUEST_NAME_LEN,
    MAX_PROPERTY_ID_LEN,
)

logger = logging.getLogger(__name__)


class VrboParsingError(Exception):
    pass


# ---------------------------------------------------------------------------
# VRBO booking ID format: "HA-" followed by 6 uppercase alphanumeric chars.
# Examples seen in the wild: HA-GN9HLB, HA-L745BN.
# ---------------------------------------------------------------------------
VRBO_BOOKING_ID_RE = re.compile(r"^HA-[A-Z0-9]{6}$")

# VRBO property IDs are purely numeric (e.g. 4989700, 4034088).
VRBO_PROPERTY_ID_RE = re.compile(r"^\d{5,10}$")


def _extract_booking_id(email_text: str) -> str:
    """
    Extract booking ID from the 'Reservation ID' section.
    Walks forward from the label to the first non-empty line.
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
    Handles two formats:
      Case 1 — inline:   "Property #4989700"
      Case 2 — two-line: "Property" on one line, "#4989700" on the next
    """

    # Case 1: inline "Property #4989700"
    match = re.search(r"property\s*#\s*(\d+)", email_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Case 2: label and ID on separate lines
    lines = email_text.splitlines()
    for i, line in enumerate(lines):
        if "property" in line.lower():
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                match = re.search(r"#\s*(\d+)", candidate)
                if match:
                    return match.group(1)

    raise VrboParsingError("Property ID not found in Vrbo email.")


def _extract_dates(email_text: str):
    """
    Extract check-in and check-out dates from a Vrbo email.

    Handles two formats:
      Case 1 — subject/inline: "Feb 21 - Mar 24, 2026"
      Case 2 — table block:    "Dates\\nApr 9 - Apr 12, 2026, 3 nights"

    FIX (cross-year stays): When borrowing the year from check-out for
    check-in, if the resulting check_in > check_out then we subtract one
    year from check_in. This correctly handles e.g. Dec 28 → Jan 3 stays.
    """

    # Case 1: inline date range "Mon DD - Mon DD, YYYY"
    match = re.search(
        r"([A-Za-z]{3,9}\s\d{1,2})\s*-\s*([A-Za-z]{3,9}\s\d{1,2},\s\d{4})",
        email_text,
    )

    if match:
        check_in_raw  = match.group(1)
        check_out_raw = match.group(2)

        # Borrow the year from check_out if check_in has none
        if "," not in check_in_raw:
            year = check_out_raw.split(",")[1].strip()
            check_in_raw = f"{check_in_raw}, {year}"

        check_in  = normalize_date(check_in_raw,  VrboParsingError)
        check_out = normalize_date(check_out_raw, VrboParsingError)

        # FIX: Detect cross-year stays (e.g. Dec 28 → Jan 3).
        # If borrowing the year produces check_in > check_out, the stay
        # spans a year boundary — subtract one year from check_in.
        if check_in > check_out:
            check_in = check_in.replace(year=check_in.year - 1)
            logger.debug(
                "Cross-year stay detected — adjusted check-in year to %d.",
                check_in.year,
            )

        return check_in, check_out

    # Case 2: "Dates\nApr 9 - Apr 12, 2026, 3 nights"
    block_match = re.search(
        r"Dates\s*\n\s*(.*?)\n",
        email_text,
        re.IGNORECASE,
    )

    if block_match:
        dates_line = block_match.group(1)
        date_range = dates_line.split(",")[0]   # strip "3 nights" suffix
        parts = date_range.split(" - ")

        if len(parts) != 2:
            raise VrboParsingError(
                f"Could not split date range into two parts: {date_range!r}"
            )

        check_in_raw, check_out_raw = parts
        check_in  = normalize_date(check_in_raw.strip(),  VrboParsingError)
        check_out = normalize_date(check_out_raw.strip(), VrboParsingError)

        return check_in, check_out

    raise VrboParsingError("Reservation dates not found in Vrbo email.")


def _extract_guest_name(email_text: str) -> str:
    """
    Extract traveler name from Vrbo email.
    Walks forward from the 'Traveler Name' label to the first non-empty line.
    """
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "traveler name" in line.lower():
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                return lines[j].strip().title()

    raise VrboParsingError("Traveler Name not found in Vrbo email.")


def parse_vrbo(email_text: str) -> dict:
    """
    Parse a Vrbo booking confirmation email.
    Returns a standardised booking dict.
    """

    # FIX 1: Size guard — first line of defence against ReDoS.
    check_email_size(email_text, VrboParsingError)

    # FIX 2: Normalise line endings and strip control characters.
    email_text = normalize_email_text(email_text)

    # Quick pre-check — avoids running all extractors on irrelevant emails.
    if "reservation id" not in email_text.lower():
        raise VrboParsingError("Not a Vrbo reservation email.")

    # --- Booking ID ---
    booking_id = _extract_booking_id(email_text)
    booking_id = cap_field(booking_id, MAX_BOOKING_ID_LEN, "Booking ID", VrboParsingError)

    # FIX 3: Validate booking ID format.
    if not VRBO_BOOKING_ID_RE.fullmatch(booking_id):
        raise VrboParsingError(
            f"Booking ID has unexpected format: {booking_id!r}. "
            "Expected format: HA-XXXXXX (6 uppercase alphanumeric chars)."
        )

    # --- Property ID ---
    property_id = _extract_property_id(email_text)
    property_id = cap_field(property_id, MAX_PROPERTY_ID_LEN, "Property ID", VrboParsingError)

    # FIX 4: Validate property ID is purely numeric.
    if not VRBO_PROPERTY_ID_RE.fullmatch(property_id):
        raise VrboParsingError(
            f"Property ID has unexpected format: {property_id!r}. "
            "Expected 5–10 digit numeric ID."
        )

    # --- Guest name ---
    guest_name = _extract_guest_name(email_text)
    guest_name = cap_field(guest_name, MAX_GUEST_NAME_LEN, "Guest Name", VrboParsingError)

    # --- Dates ---
    check_in, check_out = _extract_dates(email_text)

    # FIX 5: Validate date range — catches inverted dates and year-parsing bugs.
    validate_date_range(check_in, check_out, VrboParsingError)

    return {
        "platform":             "vrbo",
        "booking_id":           booking_id,
        "platform_property_id": property_id,
        "guest_name":           guest_name,
        "check_in":             check_in.isoformat(),
        "check_out":            check_out.isoformat(),
    }