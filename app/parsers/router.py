import logging

from .airbnb import parse_airbnb, parse_airbnb_cancellation, AirbnbParsingError
from .vrbo import parse_vrbo, parse_vrbo_cancellation, VrboParsingError
from .booking import parse_booking, BookingParsingError
from app.parsers.utils import normalize_email_text


logger = logging.getLogger(__name__)


class UnsupportedEmailError(Exception):
    pass


class NonBookingEmailError(Exception):
    """
    Raised when an email is from a known platform but is not a booking-relevant
    email — e.g. a guest message reply, a payment receipt, a review request.

    Unlike UnsupportedEmailError (which goes to failed_emails),
    NonBookingEmailError is silently skipped and the email is marked as
    processed so it doesn't appear again.
    """
    pass


# ---------------------------------------------------------------------------
# NON-BOOKING PHRASES
# Emails containing these phrases are legitimate platform emails but not
# booking confirmations or cancellations. They should be silently skipped.
# Add phrases as you encounter new email types in the wild.
# ---------------------------------------------------------------------------
NON_BOOKING_PHRASES = {
    "vrbo": [
        "has replied to your message",
        "sent you a message",
        "new message from",
        "payment has been processed",
        "payout has been sent",
        "left you a review",
        "review reminder",
        "complete your listing",
        "tips for hosting",
    ],
    "airbnb": [
        "sent you a message",
        "you have a new message",
        "left you a review",
        "review reminder",
        "your payout",
        "upcoming trip reminder",
        "checkout reminder",
    ],
    "booking": [
        "new message from your guest",
        "guest has left a review",
        "payment confirmation",
    ],
}

# ---------------------------------------------------------------------------
# CANCELLATION PHRASES
# ---------------------------------------------------------------------------
CANCELLATION_PHRASES = {
    "airbnb": [
        "reservation canceled",
        "reservation cancelled",
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

# ---------------------------------------------------------------------------
# SENDER DOMAIN → PLATFORM MAP
# Uses base domain matching (subdomains included).
# e.g. "messages.homeaway.com" → "vrbo"
#      "guest.booking.com"     → "booking"
# ---------------------------------------------------------------------------
DOMAIN_PLATFORM_MAP = {
    "airbnb.com":   "airbnb",
    "vrbo.com":     "vrbo",
    "homeaway.com": "vrbo",
    "booking.com":  "booking",
}


def _platform_from_domain(sender_domain: str) -> str | None:
    """Return platform name if sender_domain matches or is subdomain of a known base domain."""
    for base, platform in DOMAIN_PLATFORM_MAP.items():
        if sender_domain == base or sender_domain.endswith("." + base):
            return platform
    return None


def _is_non_booking(platform: str, lower_text: str) -> bool:
    """Return True if this is a known non-booking email (message, review, payout etc.)"""
    for phrase in NON_BOOKING_PHRASES.get(platform, []):
        if phrase in lower_text:
            return True
    return False


def _is_cancellation(platform: str, lower_text: str) -> bool:
    """Return True if any known cancellation phrase is found for this platform."""
    for phrase in CANCELLATION_PHRASES.get(platform, []):
        if phrase in lower_text:
            return True
    return False


def detect_platform(email_text: str, sender_domain: str = "") -> str:
    """
    Detect which booking platform sent this email.
    Primary: sender domain (subdomain-aware).
    Fallback: body-text keyword matching.
    """
    # Primary: sender domain
    if sender_domain:
        platform = _platform_from_domain(sender_domain)
        if platform:
            logger.debug("Platform detected via sender domain: %s → %s", sender_domain, platform)
            return platform

    # Fallback: body text
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

    Raises:
        NonBookingEmailError  — known platform, irrelevant email (skip silently)
        UnsupportedEmailError — unknown platform or unimplemented parser
        AirbnbParsingError / VrboParsingError / BookingParsingError — parse failure
    """
    email_text = normalize_email_text(email_text)
    lower_text = email_text.lower()

    platform = detect_platform(email_text, sender_domain)

    # --- Non-booking check (MUST run before cancellation and confirmation) ---
    # Silently skip message replies, reviews, payouts etc.
    if _is_non_booking(platform, lower_text):
        raise NonBookingEmailError(
            f"[{platform}] Non-booking email detected "
            f"(message reply / review / payout). Skipping silently."
        )

    logger.info("Routing email to platform parser: %s", platform)

    # --- Cancellation detection ---
    if _is_cancellation(platform, lower_text):
        logger.info("Email identified as cancellation for platform: %s", platform)

        if platform == "airbnb":
            return parse_airbnb_cancellation(email_text)

        elif platform == "vrbo":
            return parse_vrbo_cancellation(email_text)

        elif platform == "booking":
            raise UnsupportedEmailError(
                "Booking.com cancellation email detected but parser not yet implemented."
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
        raise type(e)(f"[{platform}] {e}") from e

    raise UnsupportedEmailError(
        f"No parser implemented for platform: {platform!r}"
    )