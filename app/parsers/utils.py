# app/parsers/utils.py
#
# Shared utilities for all platform email parsers.
# Centralises logic that was previously duplicated across airbnb.py and vrbo.py.

import re
from datetime import date
from app.utils import date_utils


# ---------------------------------------------------------------------------
# INPUT LIMITS
# 50 KB is generous for any booking confirmation email (real ones are <20 KB).
# Anything larger is either a spam/attack email or a deeply nested forward —
# neither should be parsed. This prevents catastrophic regex backtracking
# (ReDoS) on crafted inputs.
# ---------------------------------------------------------------------------
MAX_EMAIL_BYTES = 50_000

# Field length caps — anything beyond these is garbage, not a real value.
MAX_BOOKING_ID_LEN   = 20
MAX_GUEST_NAME_LEN   = 80
MAX_PROPERTY_NAME_LEN = 120
MAX_PROPERTY_ID_LEN  = 20


def normalize_email_text(text: str) -> str:
    """
    Normalize raw email text before any parsing begins.

    Fixes:
    - Mixed line endings (\r\n, \r) → \n  so regex line anchors work reliably
    - Null bytes → removed            (corrupt emails / encoding artifacts)
    - Unicode directional overrides → removed  (invisible chars that confuse
      regex and can be used to spoof displayed content vs parsed content)
    """
    # Normalize line endings first
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove null bytes
    text = text.replace("\x00", "")

    # Remove Unicode format/directional override characters (category Cf)
    # but keep tabs and newlines which are category Cc but needed for parsing.
    import unicodedata
    text = "".join(
        c for c in text
        if unicodedata.category(c) != "Cf" or c in ("\n", "\t")
    )

    return text.strip()


def check_email_size(text: str, error_class: type) -> None:
    """
    Raise error_class if the email body exceeds MAX_EMAIL_BYTES.
    Call this as the very first step in every parse_*() function.
    """
    if len(text.encode("utf-8")) > MAX_EMAIL_BYTES:
        raise error_class(
            f"Email body exceeds maximum allowed size ({MAX_EMAIL_BYTES} bytes). "
            "Refusing to parse."
        )


def normalize_date(date_str: str, error_class: type) -> date:
    """
    Parse a raw date string into a datetime.date.
    Raises error_class with a clear message on failure.

    FIX: Was duplicated identically in airbnb.py and vrbo.py.
    Now lives here and is imported by both.
    Returns a date object (not a string) so callers can do arithmetic
    (e.g. check_out > check_in) before converting to ISO format.
    """
    try:
        parsed = date_utils.parse(date_str, fuzzy=True)
        return parsed.date()
    except Exception:
        raise error_class(f"Invalid date format: {date_str!r}")


def validate_date_range(check_in: date, check_out: date, error_class: type) -> None:
    """
    Validate that check_out is strictly after check_in, and that neither
    date is absurdly far in the future (catches year-parsing bugs).

    FIX: Neither parser previously validated date ordering. A mis-parsed
    year could produce check_in > check_out silently stored in the DB.
    """
    if check_out <= check_in:
        raise error_class(
            f"Check-out ({check_out}) must be after check-in ({check_in})."
        )

    today = date.today()
    if check_in < today.replace(year=today.year - 1):
        raise error_class(
            f"Check-in date ({check_in}) is more than a year in the past — "
            "likely a parsing error."
        )

    if check_out > today.replace(year=today.year + 3):
        raise error_class(
            f"Check-out date ({check_out}) is more than 3 years in the future — "
            "likely a parsing error."
        )


def cap_field(value: str, max_len: int, field_name: str, error_class: type) -> str:
    """
    Raise error_class if value exceeds max_len characters.
    Prevents oversized strings from reaching the database.
    """
    if len(value) > max_len:
        raise error_class(
            f"{field_name} exceeds maximum length ({max_len} chars). "
            f"Got {len(value)} chars — likely a parsing error."
        )
    return value