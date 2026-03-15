from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import date
from typing import Optional

from app.db.models import Booking, Property, ProcessedEmail, BookingStatus


# ---------------------------
# PROPERTY
# ---------------------------

def get_or_create_property(db: Session, property_name: str) -> Property:
    property_obj = (
        db.query(Property)
        .filter(Property.name == property_name)
        .first()
    )

    if property_obj:
        return property_obj

    property_obj = Property(name=property_name)
    db.add(property_obj)
    db.flush()

    return property_obj


def get_property_by_vrbo_code(db: Session, vrbo_code: str) -> Optional[Property]:
    """
    Look up a Property by its Vrbo numeric code (e.g. "4034088" → Stassen).
    Returns None if the code is not in the DB — caller decides how to handle.
    """
    return (
        db.query(Property)
        .filter(Property.vrbo_code == vrbo_code)
        .first()
    )


# ---------------------------
# EMAIL IDEMPOTENCY
# ---------------------------

def is_email_processed(db: Session, message_id: str) -> bool:
    return (
        db.query(ProcessedEmail)
        .filter(ProcessedEmail.message_id == message_id)
        .first()
        is not None
    )


def mark_email_processed(db: Session, message_id: str, platform: str):
    processed = ProcessedEmail(
        message_id=message_id,
        platform=platform,
    )
    db.add(processed)


# ---------------------------
# BOOKING UPSERT
# ---------------------------

def upsert_booking(
    db: Session,
    booking_id: str,
    platform: str,
    property_id: int,
    guest_name: Optional[str],
    checkin_date: date,
    checkout_date: date,
    status: BookingStatus,
    message_id: str,
):
    existing_booking = (
        db.query(Booking)
        .filter(
            Booking.booking_id == booking_id,
            Booking.platform == platform,
        )
        .first()
    )

    if existing_booking:
        existing_booking.guest_name = guest_name
        existing_booking.checkin_date = checkin_date
        existing_booking.checkout_date = checkout_date
        existing_booking.status = status
        existing_booking.last_email_message_id = message_id
        return existing_booking

    new_booking = Booking(
        booking_id=booking_id,
        platform=platform,
        property_id=property_id,
        guest_name=guest_name,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        status=status,
        last_email_message_id=message_id,
    )

    db.add(new_booking)
    db.flush()

    return new_booking


# ---------------------------
# CANCEL BOOKING
# ---------------------------

def cancel_booking(
    db: Session,
    booking_id: str,
    platform: str,
    message_id: str,
):
    booking = (
        db.query(Booking)
        .filter(
            Booking.booking_id == booking_id,
            Booking.platform == platform,
        )
        .first()
    )

    if not booking:
        raise ValueError(
            f"Booking {booking_id} on {platform} not found for cancellation."
        )

    booking.status = BookingStatus.cancelled
    booking.last_email_message_id = message_id

    return booking