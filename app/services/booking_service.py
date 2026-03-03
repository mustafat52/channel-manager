from datetime import datetime
from sqlalchemy.orm import Session

from app.parsers.router import parse_email
from app.db.models import BookingStatus
from app.db import crud



class EmailAlreadyProcessed(Exception):
    pass


class UnsupportedPlatformForInsert(Exception):
    pass


def _convert_to_date(date_str: str):
    """
    Converts YYYY-MM-DD string to datetime.date.
    """
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def process_email(
    db: Session,
    email_text: str,
    message_id: str,
):
    """
    Main entry point:
    Takes raw email + message_id
    Parses and persists booking
    """

    # ---------------------------
    # 1️⃣ Idempotency Check
    # ---------------------------
    if crud.is_email_processed(db, message_id):
        raise EmailAlreadyProcessed(
            f"Email {message_id} already processed."
        )

    # ---------------------------
    # 2️⃣ Parse Email
    # ---------------------------
    parsed = parse_email(email_text)

    platform = parsed["platform"]

    # ---------------------------
    # Handle Cancellation
    # ---------------------------
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
        return booking

    # Skip Booking.com for now
    if platform == "booking":
        raise UnsupportedPlatformForInsert(
            "Booking.com parsing incomplete — skipping insert."
        )

    # ---------------------------
    # 3️⃣ Convert Dates
    # ---------------------------
    checkin_date = _convert_to_date(parsed["check_in"])
    checkout_date = _convert_to_date(parsed["check_out"])

    # ---------------------------
    # 4️⃣ Resolve Property
    # ---------------------------
    if platform == "vrbo":
        property_identifier = parsed.get("platform_property_id") or parsed.get("property_id")
        property_name = f"vrbo_property_{property_identifier}"
    else:
        property_name = parsed["property_name"]

    property_obj = crud.get_or_create_property(
        db=db,
        property_name=property_name,
    )

    # ---------------------------
    # 5️⃣ Upsert Booking
    # ---------------------------
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

    # ---------------------------
    # 6️⃣ Mark Email Processed
    # ---------------------------
    crud.mark_email_processed(
        db=db,
        message_id=message_id,
        platform=platform,
    )

    # ---------------------------
    # 7️⃣ Commit Transaction
    # ---------------------------
    db.commit()

    return booking