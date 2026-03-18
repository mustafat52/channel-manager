import logging

from .airbnb import parse_airbnb, parse_airbnb_cancellation, AirbnbParsingError
from .vrbo import parse_vrbo, parse_vrbo_cancellation, VrboParsingError
from .booking import parse_booking, BookingParsingError
from app.parsers.utils import normalize_email_text


logger = logging.getLogger(__name__)


class UnsupportedEmailError(Exception):
    pass


# ---------------------------------------------------------------------------
# CANCELLATION PHRASES
# FIX: Cancellation detection was only implemented for Airbnb. A VRBO
# cancellation email would fall through to parse_vrbo() which would either
# fail loudly or — worse — store it as a confirmed booking.
#
# Each platform uses different language in their cancellation emails.
# Add phrases here as you encounter new formats in the wild.
# ---------------------------------------------------------------------------
CANCELLATION_PHRASES = {
    "airbnb": [
        "reservation canceled",
        "reservation cancelled",       # Airbnb uses both spellings
        "your reservation has been canceled",
    ],
    "vrbo": [
        "reservation was canceled",
        "reservation was cancelled",
        "your reservation was canceled",
        "your reservation was cancelled",
        "reservation has been cancelled",
        "reservation has been canceled",
        "booking has been cancelled",
        "booking has been canceled",
    ],
    "booking": [
        "reservation is cancelled",
        "reservation is canceled",
        "booking is cancelled",
        "booking is canceled",
    ],
}


def _is_cancellation(platform: str, lower_text: str) -> bool:
    """Return True if any known cancellation phrase is found for this platform."""
    for phrase in CANCELLATION_PHRASES.get(platform, []):
        if phrase in lower_text:
            return True
    return False


def detect_platform(email_text: str, sender_domain: str = "") -> str:
    """
    Detect which booking platform sent this email.

    FIX 1: Now accepts an optional sender_domain argument (passed from
    gmail_client via the email dict). When present, domain-based detection
    runs first — it's more reliable than body-text matching because a guest
    could mention a competitor platform in the body of their message.

    FIX 2: Body-text detection is kept as a fallback for cases where the
    sender domain is unavailable (e.g. forwarded emails, future platforms).

    FIX 3: Removed bare `import re` that was imported but never used.
    """

    # --- Primary: sender domain (fast, unambiguous) ---
    domain_map = {
        "airbnb.com":    "airbnb",
        "vrbo.com":      "vrbo",
        "homeaway.com":  "vrbo",
        "booking.com":   "booking",
    }
    if sender_domain and sender_domain in domain_map:
        platform = domain_map[sender_domain]
        logger.debug("Platform detected via sender domain: %s → %s", sender_domain, platform)
        return platform

    # --- Fallback: body-text keyword matching ---
    lower_text = email_text.lower()

    if "airbnb" in lower_text:
        logger.debug("Platform detected via body text: airbnb")
        return "airbnb"

    if "vrbo" in lower_text or "homeaway" in lower_text:
        logger.debug("Platform detected via body text: vrbo")
        return "vrbo"

    if "booking confirmation" in lower_text and "booking.com" in lower_text:
        logger.debug("Platform detected via body text: booking")
        return "booking"

    raise UnsupportedEmailError(
        "Could not determine booking platform from email. "
        f"Sender domain: {sender_domain!r}"
    )


def parse_email(email_text: str, sender_domain: str = "") -> dict:
    """
    Main entry point — parse any booking confirmation or cancellation email.
    Returns a standardised booking dict.

    Args:
        email_text:    Plain-text body of the email.
        sender_domain: Domain from the From header (e.g. 'airbnb.com').
                       Optional but improves platform detection accuracy.
    """

    # Normalise line endings and strip control characters once here,
    # before platform detection or any parser runs.
    # The individual parsers also call this, so double-normalising is safe.
    email_text = normalize_email_text(email_text)
    lower_text = email_text.lower()

    platform = detect_platform(email_text, sender_domain)
    logger.info("Routing email to platform parser: %s", platform)

    # --- Cancellation detection (must run before confirmation parsing) ---
    # FIX: Was only checked for Airbnb. Now checked for all platforms.
    if _is_cancellation(platform, lower_text):
        logger.info("Email identified as cancellation for platform: %s", platform)

        if platform == "airbnb":
            return parse_airbnb_cancellation(email_text)

        elif platform == "vrbo":
            return parse_vrbo_cancellation(email_text)

        elif platform == "booking":
            raise UnsupportedEmailError(
                "Booking.com cancellation email detected but parser not yet implemented. "
                "Email saved to failed_emails for manual review."
            )

    # --- Confirmation parsing ---
    try:
        if platform == "airbnb":
            return parse_airbnb(email_text)

        elif platform == "vrbo":
            return parse_vrbo(email_text)

        elif platform == "booking":
            return parse_booking(email_text)

    except (AirbnbParsingError, VrboParsingError, BookingParsingError) as e:
        # FIX: Re-raise with platform context so the worker log shows
        # WHICH platform failed, not just a bare field-not-found message.
        raise type(e)(f"[{platform}] {e}") from e

    raise UnsupportedEmailError(
        f"No parser implemented for platform: {platform!r}"
    )