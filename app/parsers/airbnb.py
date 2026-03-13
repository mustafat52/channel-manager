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


# ---------------------------------------------------------------------------
# Airbnb booking ID format: uppercase alphanumeric, 6–12 characters.
# Examples seen in the wild: HMSMRP35HP (10 chars).
# Reject anything outside this shape before it reaches the database.
# ---------------------------------------------------------------------------
AIRBNB_BOOKING_ID_RE = re.compile(r"^[A-Z0-9]{6,12}$")


def _extract_with_regex(pattern: str, text: str, field_name: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise AirbnbParsingError(f"{field_name} not found in Airbnb email.")
    return match.group(1).strip()


def _clean_property_name(name: str) -> str:
    """Remove Airbnb promotional text and stray HTML fragments."""
    name = name.strip()
    name = re.sub(r"<.*?>", "", name)       # strip inline HTML tags
    if " l " in name:
        name = name.split(" l ")[0].strip() # remove promotional suffix
    name = name.rstrip("!").strip()
    return name


def _extract_guest_name(email_text: str) -> str:
    """
    Extract guest name by locating 'Identity verified' or 'reviews'
    and walking backwards to the first non-URL, non-empty line.

    FIX: Added a sanity check on the extracted candidate — if it looks like
    a URL, is longer than MAX_GUEST_NAME_LEN, or contains digits mixed with
    letters in a URL-like pattern, we keep walking rather than returning garbage.
    """
    lines = email_text.splitlines()

    for i, line in enumerate(lines):
        if "Identity verified" in line or "reviews" in line:
            j = i - 1

            while j >= 0:
                candidate = lines[j].strip()

                if not candidate:
                    j -= 1
                    continue

                if candidate.startswith("<http") or "airbnb.com" in candidate:
                    j -= 1
                    continue

                # FIX: Sanity check — a real name won't exceed the length cap
                # and won't look like a URL or contain angle brackets.
                if len(candidate) > MAX_GUEST_NAME_LEN:
                    logger.warning(
                        "Airbnb guest name candidate too long (%d chars), skipping line.",
                        len(candidate)
                    )
                    j -= 1
                    continue

                if re.search(r"https?://|www\.", candidate, re.IGNORECASE):
                    j -= 1
                    continue

                return candidate

    raise AirbnbParsingError("Guest Name not found in Airbnb email.")


def parse_airbnb(email_text: str) -> dict:
    """
    Parse an Airbnb booking confirmation email.
    Returns a standardised booking dict.
    """

    # FIX 1: Size guard — must be first, before any regex runs.
    # Prevents ReDoS on crafted oversized inputs.
    check_email_size(email_text, AirbnbParsingError)

    # FIX 2: Normalize line endings and strip control characters so that
    # regex line anchors (\n) work reliably on all email clients/forwarders.
    email_text = normalize_email_text(email_text)

    # --- Booking ID ---
    booking_id = _extract_with_regex(
        r"Confirmation code\s*\n+\s*([A-Z0-9]+)",
        email_text,
        "Booking ID",
    )

    # FIX 3: Validate booking ID format before accepting it.
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
    property_name = _extract_with_regex(
        r"\n\s*([^\n]+)\s*\n(?:https?:\/\/[^\n]+\n)?\s*Entire",
        email_text,
        "Property Name",
    )
    property_name = _clean_property_name(property_name)
    property_name = cap_field(
        property_name, MAX_PROPERTY_NAME_LEN, "Property Name", AirbnbParsingError
    )

    # --- Dates ---
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

    check_in  = normalize_date(check_in_raw,  AirbnbParsingError)
    check_out = normalize_date(check_out_raw, AirbnbParsingError)

    # FIX 4: Validate date range — catch_out must be after check_in.
    # Also catches year-parsing bugs (e.g. fuzzy parser picks wrong year).
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

    Based on real sample — the cancellation email contains:
      Subject: Canceled: Reservation HM4FSJ3NHZ for Mar 1 – 27, 2026
      Body:    "cancel reservation HM4FSJ3NHZ for Mar 1 – 27"
               "your guest Chris had to cancel reservation HM4FSJ3NHZ"
               Property name appears at the top of the body.

    We try three extraction strategies in order of reliability:
      1. Inline sentence: "cancel reservation XXXXXXXXXX"  (most specific)
      2. Standalone label: "Reservation XXXXXXXXXX"        (original pattern)
      3. Subject line:     "Canceled: Reservation XXXXXX"  (fallback)

    Also extracts guest name and property name from the cancellation email
    so your dashboard can display full cancellation details without needing
    to look up the original booking (useful when the original booking ID
    doesn't exist in the DB yet, e.g. during testing).
    """

    check_email_size(email_text, AirbnbParsingError)
    email_text = normalize_email_text(email_text)

    # --- Booking ID: try three patterns in order ---
    booking_id = None

    # Pattern 1: "cancel reservation HM4FSJ3NHZ" (inline sentence, most reliable)
    match = re.search(r"cancel(?:ed|led)?\s+reservation\s+([A-Z0-9]{6,12})", email_text, re.IGNORECASE)
    if match:
        booking_id = match.group(1).upper()

    # Pattern 2: standalone "Reservation XXXXXXXXXX" on its own line
    if not booking_id:
        match = re.search(r"^Reservation\s+([A-Z0-9]{6,12})\s*$", email_text, re.MULTILINE)
        if match:
            booking_id = match.group(1).upper()

    # Pattern 3: subject line "Canceled: Reservation XXXXXXXXXX for ..."
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

    # --- Guest name: "your guest Chris had to cancel" ---
    guest_name = None
    match = re.search(r"your guest\s+([A-Za-z][A-Za-z\s\-']{0,50})\s+had to cancel", email_text, re.IGNORECASE)
    if match:
        guest_name = match.group(1).strip().title()

    # --- Property name: appears as the first non-empty line after "Reservation canceled" ---
    property_name = None
    lines = email_text.splitlines()
    for i, line in enumerate(lines):
        if "reservation canceled" in line.lower():
            # Next non-empty line is the property name
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()
                if candidate and len(candidate) <= MAX_PROPERTY_NAME_LEN:
                    property_name = _clean_property_name(candidate)
                    break
            break

    result = {
        "platform":   "airbnb",
        "booking_id": booking_id,
        "status":     "cancelled",
    }

    # These are bonus fields — include them if found, don't fail if not.
    # Your booking_service can use them to enrich the cancellation record
    # or match against an existing booking.
    if guest_name:
        result["guest_name"] = guest_name
    if property_name:
        result["property_name"] = property_name

    return result