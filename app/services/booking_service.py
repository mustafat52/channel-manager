"""
booking_service.py

Handles email parsing and booking persistence only.
All notification responsibility is delegated to notification_service.
"""

from datetime import datetime
from sqlalchemy.orm import Session

from app.parsers.router import parse_email
from app.db.models import BookingStatus, FailedEmail
from app.db import crud
from app.services.notification_service import notify_new_booking, notify_cancellation


class EmailAlreadyProcessed(Exception):
    pass


class UnsupportedPlatformForInsert(Exception):
    pass


class UnknownVrboProperty(Exception):
    pass


def _convert_to_date(date_str: str):
    """Converts YYYY-MM-DD string to datetime.date."""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def process_email(
    db: Session,
    email_text: str,
    message_id: str,
):
    """
    Entry point for all email-sourced bookings.

    Flow:
        1. Idempotency check
        2. Parse email
        3. Persist to DB
        4. Delegate notification to notification_service

    Notifications read from the Booking object — not from raw email data.
    This means email-sourced and manually-entered bookings produce
    identical notification behaviour.
    """

    # ── 1. Idempotency ────────────────────────────────────────────────
    if crud.is_email_processed(db, message_id):
        raise EmailAlreadyProcessed(
            f"Email {message_id} already processed."
        )

    # ── 2. Parse ──────────────────────────────────────────────────────
    parsed = parse_email(email_text)
    platform = parsed["platform"]

    # ── 3a. Cancellation path ─────────────────────────────────────────
    if parsed.get("status") == "cancelled":
        booking = crud.cancel_booking(
            db=db,
            booking_id=parsed["booking_id"],
            platform=platform,
            message_id=message_id,
        )

        crud.mark_email_processed(
            db=db,
            message_id=message_id,
            platform=platform,
        )

        db.commit()

        notify_cancellation(db=db, booking=booking)

        return booking

    # ── 3b. Skip Booking.com emails (manual entry handles these) ──────
    if platform == "booking":
        raise UnsupportedPlatformForInsert(
            "Booking.com parsing incomplete — skipping insert."
        )

    # ── 4. Convert dates ──────────────────────────────────────────────
    checkin_date  = _convert_to_date(parsed["check_in"])
    checkout_date = _convert_to_date(parsed["check_out"])

    # ── 5. Resolve property ───────────────────────────────────────────
    if platform == "vrbo":
        vrbo_code = (
            parsed.get("platform_property_id") or parsed.get("property_id")
        )

        # Look up by the numeric Vrbo code stored in the properties table.
        # If the code isn't seeded yet, fail loudly so it gets added.
        property_obj = crud.get_property_by_vrbo_code(db, vrbo_code)

        if property_obj is None:
            raise UnknownVrboProperty(
                f"Vrbo property code '{vrbo_code}' not found in the properties table. "
                f"Add it via the seed script (scripts/seed_properties.py)."
            )

    else:
        property_name = parsed["property_name"]
        property_obj = crud.get_or_create_property(db=db, property_name=property_name)

    # ── 6. Upsert booking ─────────────────────────────────────────────
    booking = crud.upsert_booking(
        db=db,
        booking_id=parsed["booking_id"],
        platform=platform,
        property_id=property_obj.id,
        guest_name=parsed.get("guest_name"),
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        status=BookingStatus.confirmed,
        message_id=message_id,
    )

    # ── 7. Mark email processed ───────────────────────────────────────
    crud.mark_email_processed(
        db=db,
        message_id=message_id,
        platform=platform,
    )

    # ── 8. Commit ─────────────────────────────────────────────────────
    db.commit()

    # ── 9. Notify ─────────────────────────────────────────────────────
    notify_new_booking(db=db, booking=booking)

    return booking


def store_failed_email(db, message_id, email_body, error_message):
    failed = FailedEmail(
        message_id=message_id,
        email_body=email_body,
        error_message=error_message,
    )
    db.add(failed)
    db.commit()