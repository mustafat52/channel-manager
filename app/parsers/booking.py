

import re


class BookingParsingError(Exception):
    pass


def _extract_booking_id(email_text: str) -> str:
    match = re.search(
        r"Booking confirmation\s+—\s+(\d+)",
        email_text,
        re.IGNORECASE,
    )
    if not match:
        raise BookingParsingError("Booking ID not found in Booking.com email.")
    return match.group(1).strip()


def _extract_hotel_id(email_text: str) -> str | None:
    """
    Extract hotel_id from extranet URL if present.
    """
    match = re.search(
        r"hotel_id=(\d+)",
        email_text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _extract_property_name(email_text: str) -> str | None:
    """
    Extract property title from header line:
    Booking.com  Property Name
    """
    match = re.search(
        r"Booking\.com\s+(.+)",
        email_text,
        re.IGNORECASE,
    )

    if match:
        property_name = match.group(1).strip()

        # Remove trailing parts like IATA/TIDS if attached
        property_name = property_name.split("Booking confirmation")[0].strip()
        return property_name

    return None


def parse_booking(email_text: str) -> dict:
    """
    Parses Booking.com notification email.
    Returns minimal booking info.
    """

    booking_id = _extract_booking_id(email_text)
    hotel_id = _extract_hotel_id(email_text)
    property_name = _extract_property_name(email_text)

    return {
        "platform": "booking",
        "booking_id": booking_id,
        "platform_property_id": hotel_id,
        "property_name": property_name,
        "guest_name": None,
        "check_in": None,
        "check_out": None,
        "status": "pending_details",
    }