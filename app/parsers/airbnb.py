import re
import logging

from app.parsers.utils import (
    normalize_email_text,
    check_email_size,
    normalize_date,
    validate_date_range,
    cap_field,
    MAX_BOOKING_ID_LEN,
    MAX_GUEST_NAME_LEN,
    MAX_PROPERTY_NAME_LEN,
)

logger = logging.getLogger(__name__)


class AirbnbParsingError(Exception):
    pass


AIRBNB_BOOKING_ID_RE = re.compile(r"^[A-Z0-9]{6,12}$")


def _extract_with_regex(pattern: str, text: str, field_name: str) -> str:
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    if not match:
        raise AirbnbParsingError(f"{field_name} not found in Airbnb email.")
    return match.group(1).strip()


def _clean_property_name(name: str) -> str:
    """Remove Airbnb promotional text and stray HTML/URL fragments."""
    name = name.strip()
    name = re.sub(r"<.*?>", "", name)
    name = re.sub(r"https?://\S+", "", name).strip()
    # Remove promotional suffix — both " l " (mixed case) and " L " (uppercase email)
    for sep in [" l ", " L "]:
        if sep in name:
            name = name.split(sep)[0].strip()
    name = name.rstrip("!").strip()
    return name


def _extract_booking_id(email_text: str) -> str:
    """
    Extract booking ID from Airbnb confirmation email.

    Handles two real-world formats:

    Format A (forwarded/plain text — original test samples):
        Confirmation code
        HMSMRP35HP

    Format B (direct from Airbnb — real production emails):
        CONFIRMATION CODE
        HM3YZBNRXT

    Both use the same label, just different casing and spacing.
    re.IGNORECASE handles both.
    """
    # Primary: label on one line, ID on next (both formats)
    match = re.search(
        r"Confirmation\s+code\s*\n+\s*([A-Z0-9]{6,12})",
        email_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().upper()

    # Fallback: ID appears inline after label on same line
    match = re.search(
        r"Confirmation\s+code[:\s]+([A-Z0-9]{6,12})",
        email_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().upper()

    raise AirbnbParsingError("Booking ID not found in Airbnb email.")


def _extract_guest_name(email_text: str) -> str:
    """
    Extract guest name by locating 'Identity verified' or 'reviews'
    and walking backwards to the first name-like line.

    Handles two formats:
    - Format A: name is on a clean line just above 'Identity verified'
    - Format B (production): name appears on same line as a long tracking
      URL: "https://airbnb.com/...   Jennifer Ahweyevu"
      We strip the URL and take the remaining text as the name.
    """
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "identity verified" in line.lower() or "reviews" in line.lower():
            j = i - 1
            while j >= 0:
                candidate = lines[j].strip()

                if not candidate:
                    j -= 1
                    continue

                # Skip bracketed URL lines first — these are never names
                if candidate.startswith("[") and "http" in candidate:
                    j -= 1
                    continue

                # Format B: line contains both a URL and the guest name
                # e.g. "https://airbnb.com/...   Jennifer Ahweyevu"
                # Strip the URL part and take whatever remains
                if re.search(r"https?://", candidate, re.IGNORECASE):
                    tokens = candidate.split()
                    name_tokens = [
                        t for t in tokens
                        if not re.match(r"https?://", t, re.IGNORECASE)
                    ]
                    if name_tokens:
                        name = " ".join(name_tokens).strip()
                        if 2 <= len(name) <= MAX_GUEST_NAME_LEN and not name.isupper():
                            return name
                    j -= 1
                    continue

                # Skip all-caps marketing lines like "NEW BOOKING CONFIRMED!"
                if candidate.isupper():
                    j -= 1
                    continue

                if len(candidate) > MAX_GUEST_NAME_LEN:
                    logger.warning(
                        "Airbnb guest name candidate too long (%d chars), skipping.",
                        len(candidate)
                    )
                    j -= 1
                    continue

                return candidate

    raise AirbnbParsingError("Guest Name not found in Airbnb email.")


def _extract_property_name(email_text: str) -> str:
    """
    Extract property name from Airbnb email.

    Format A (plain text): property name appears just before 'Entire home/apt'
        Urban Elite 3BR Suite l W/ 30 Days Deals!
        Entire home/apt

    Format B (production): property name is UPPERCASE, preceded by a URL,
        followed by another URL, then 'Entire home/apt'
        URBAN ELITE 3BR SUITE L W/ 30 DAYS DEALS!
        Entire home/apt
    """
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "entire home" in line.lower() or "entire apt" in line.lower():
            # Walk backwards to find the property name
            j = i - 1
            while j >= 0:
                candidate = lines[j].strip()

                if not candidate:
                    j -= 1
                    continue

                # Skip URL lines
                if re.search(r"https?://|www\.", candidate, re.IGNORECASE):
                    j -= 1
                    continue

                # Skip bracketed URL lines
                if candidate.startswith("[") and "http" in candidate:
                    j -= 1
                    continue

                # Skip very short lines that aren't property names
                if len(candidate) < 5:
                    j -= 1
                    continue

                # This is our property name — title-case it if all caps
                if candidate.isupper():
                    candidate = candidate.title()

                return candidate

    raise AirbnbParsingError("Property Name not found in Airbnb email.")


def _extract_dates(email_text: str):
    """
    Extract check-in and check-out dates from Airbnb email.

    Format A (stacked):
        Check-in
        Thu, Apr 23
        4:00 PM
        Checkout
        Sun, Apr 26

    Format B (side by side columns):
        Check-in      Checkout
        Thu, Apr 16   Mon, Apr 20
        4:00 PM       11:00 AM
    """
    lines = email_text.splitlines()

    # Detect Format B: "Check-in" and "Checkout" on the same line
    for i, line in enumerate(lines):
        if re.search(r"check-in\s+checkout", line, re.IGNORECASE):
            # Next non-empty line has both dates side by side
            for j in range(i + 1, min(i + 5, len(lines))):
                date_line = lines[j].strip()
                if not date_line:
                    continue
                # Match two dates: "Thu, Apr 16   Mon, Apr 20"
                match = re.match(
                    r"([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2})\s{2,}([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2})",
                    date_line
                )
                if match:
                    return match.group(1).strip(), match.group(2).strip()
            break

    # Format A: stacked — Check-in on one line, date on next
    check_in_raw = None
    check_out_raw = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^check-in$", stripped, re.IGNORECASE):
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if candidate and not re.match(r"^\d{1,2}:\d{2}", candidate):
                    check_in_raw = candidate
                    break

        if re.match(r"^checkout$", stripped, re.IGNORECASE):
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if candidate and not re.match(r"^\d{1,2}:\d{2}", candidate):
                    check_out_raw = candidate
                    break

    if check_in_raw and check_out_raw:
        return check_in_raw, check_out_raw

    raise AirbnbParsingError("Check-in/Check-out dates not found in Airbnb email.")


def parse_airbnb(email_text: str) -> dict:
    """
    Parse an Airbnb booking confirmation email.
    Handles both plain-text forwarded format and direct production format.
    """
    check_email_size(email_text, AirbnbParsingError)
    email_text = normalize_email_text(email_text)

    # --- Booking ID ---
    booking_id = _extract_booking_id(email_text)
    booking_id = cap_field(booking_id, MAX_BOOKING_ID_LEN, "Booking ID", AirbnbParsingError)
    if not AIRBNB_BOOKING_ID_RE.fullmatch(booking_id):
        raise AirbnbParsingError(
            f"Booking ID has unexpected format: {booking_id!r}. "
            "Expected 6–12 uppercase alphanumeric characters."
        )

    # --- Guest name ---
    guest_name = _extract_guest_name(email_text)
    guest_name = cap_field(guest_name, MAX_GUEST_NAME_LEN, "Guest Name", AirbnbParsingError)

    # --- Property name ---
    property_name = _extract_property_name(email_text)
    property_name = _clean_property_name(property_name)
    property_name = cap_field(
        property_name, MAX_PROPERTY_NAME_LEN, "Property Name", AirbnbParsingError
    )

    # --- Dates ---
    check_in_raw, check_out_raw = _extract_dates(email_text)
    check_in  = normalize_date(check_in_raw,  AirbnbParsingError)
    check_out = normalize_date(check_out_raw, AirbnbParsingError)
    validate_date_range(check_in, check_out, AirbnbParsingError)

    return {
        "platform":      "airbnb",
        "booking_id":    booking_id,
        "property_name": property_name,
        "guest_name":    guest_name,
        "check_in":      check_in.isoformat(),
        "check_out":     check_out.isoformat(),
    }


def parse_airbnb_cancellation(email_text: str) -> dict:
    """
    Parse an Airbnb cancellation email.
    Tries three extraction patterns in order of reliability.
    """
    check_email_size(email_text, AirbnbParsingError)
    email_text = normalize_email_text(email_text)

    booking_id = None

    match = re.search(r"cancel(?:ed|led)?\s+reservation\s+([A-Z0-9]{6,12})", email_text, re.IGNORECASE)
    if match:
        booking_id = match.group(1).upper()

    if not booking_id:
        match = re.search(r"^Reservation\s+([A-Z0-9]{6,12})\s*$", email_text, re.MULTILINE | re.IGNORECASE)
        if match:
            booking_id = match.group(1).upper()

    if not booking_id:
        match = re.search(r"Canceled?:\s*Reservation\s+([A-Z0-9]{6,12})", email_text, re.IGNORECASE)
        if match:
            booking_id = match.group(1).upper()

    if not booking_id:
        raise AirbnbParsingError("Booking ID not found in Airbnb cancellation email.")

    if not AIRBNB_BOOKING_ID_RE.fullmatch(booking_id):
        raise AirbnbParsingError(
            f"Cancellation booking ID has unexpected format: {booking_id!r}."
        )

    guest_name = None
    match = re.search(r"your guest\s+([A-Za-z][A-Za-z\s\-']{0,50})\s+had to cancel", email_text, re.IGNORECASE)
    if match:
        guest_name = match.group(1).strip().title()

    property_name = None
    lines = email_text.splitlines()
    for i, line in enumerate(lines):
        if "reservation canceled" in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()
                if candidate and len(candidate) <= MAX_PROPERTY_NAME_LEN:
                    if not re.search(r"https?://", candidate):
                        property_name = _clean_property_name(candidate)
                        break
            break

    result = {
        "platform":   "airbnb",
        "booking_id": booking_id,
        "status":     "cancelled",
    }
    if guest_name:
        result["guest_name"] = guest_name
    if property_name:
        result["property_name"] = property_name

    return result