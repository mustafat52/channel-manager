import re

from .airbnb import parse_airbnb, AirbnbParsingError
from .vrbo import parse_vrbo, VrboParsingError
from .booking import parse_booking, BookingParsingError


class UnsupportedEmailError(Exception):
    pass


def detect_platform(email_text: str) -> str:
    """
    Detect platform based on unique identifiers in email.
    """

    lower_text = email_text.lower()

    # Airbnb detection
    if "airbnb" in lower_text:
        return "airbnb"

    # Vrbo detection
    if "reservation id" in lower_text and "vrbo" in lower_text:
        return "vrbo"

    # Booking.com detection
    if "booking confirmation" in lower_text and "booking.com" in lower_text:
        return "booking"

    raise UnsupportedEmailError("Could not determine email platform.")

def parse_email(email_text: str) -> dict:
    """
    Main entry point for parsing any booking email.
    Returns standardized booking dictionary.
    """

    platform = detect_platform(email_text)

    # 🔴 Cancellation detection FIRST
    if platform == "airbnb" and "reservation canceled" in email_text.lower():
        from .airbnb import parse_airbnb_cancellation
        return parse_airbnb_cancellation(email_text)

    try:
        if platform == "airbnb":
            return parse_airbnb(email_text)

        elif platform == "vrbo":
            return parse_vrbo(email_text)

        elif platform == "booking":
            return parse_booking(email_text)

    except (AirbnbParsingError, VrboParsingError, BookingParsingError) as e:
        raise e

    raise UnsupportedEmailError("Parser not implemented for detected platform.")