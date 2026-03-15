"""
notification_service.py

All notifications are triggered from Booking objects in the database.
Sources (email parsing, manual entry, future APIs) are irrelevant here.

Public functions:
    notify_new_booking(db, booking)      — instant new booking alert
    notify_cancellation(db, booking)     — cancellation alert
    send_tomorrow_cleanings(db)          — scheduler: 8PM IST daily
    send_upcoming_cleanings(db)          — scheduler: 6AM IST daily
"""

import requests
from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Booking, Property, BookingStatus, NotificationLog


# ─────────────────────────────────────────────
# INTERNAL: RAW WHATSAPP SENDER
# ─────────────────────────────────────────────

def _send_whatsapp_message(message: str) -> dict:
    """
    Sends a WhatsApp text message via Meta Cloud API.
    Returns the raw API response dict.
    """
    url = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": settings.MANAGER_PHONE,
        "type": "text",
        "text": {"body": message.strip()},
    }

    print(f"[WhatsApp] Sending:\n{message.strip()}\n")

    response = requests.post(url, headers=headers, json=payload)
    result = response.json()

    print(f"[WhatsApp] Response: {result}")
    return result


# ─────────────────────────────────────────────
# INTERNAL: NOTIFICATION LOG WRITER
# ─────────────────────────────────────────────

def _log_notification(
    db: Session,
    booking_id: int,
    notification_type: str,
    delivery_status: str,
    response_payload: dict,
):
    log = NotificationLog(
        booking_id=booking_id,
        notification_type=notification_type,
        delivery_status=delivery_status,
        response_payload=response_payload,
    )
    db.add(log)
    db.commit()


# ─────────────────────────────────────────────
# 1. INSTANT BOOKING NOTIFICATION
# ─────────────────────────────────────────────

def notify_new_booking(db: Session, booking: Booking):
    """
    Sends an instant WhatsApp alert when any new booking enters the DB.

    Triggered by:
        - booking_service.process_email()
        - manual_booking.create_manual_booking()
        - any future booking source

    Guard: notified_instant flag prevents duplicate sends even if
    called multiple times for the same booking.
    """
    if booking.notified_instant:
        print(f"[Notify] Booking {booking.booking_id} already notified — skipping.")
        return

    property_name = booking.property.name if booking.property else "Unknown Property"

    checkin  = booking.checkin_date.strftime("%b %d")
    checkout = booking.checkout_date.strftime("%b %d")
    nights   = (booking.checkout_date - booking.checkin_date).days

    message = f"""📌 *NEW BOOKING — {booking.platform.capitalize()}*

🏠 {property_name}
👤 {booking.guest_name or 'N/A'}

📅 {checkin} → {checkout}  ({nights} nights)"""

    result = _send_whatsapp_message(message)

    booking.notified_instant = True
    db.commit()

    _log_notification(
        db=db,
        booking_id=booking.id,
        notification_type="instant",
        delivery_status="delivered" if "messages" in result else "failed",
        response_payload=result,
    )


# ─────────────────────────────────────────────
# 2. CANCELLATION NOTIFICATION
# ─────────────────────────────────────────────

def notify_cancellation(db: Session, booking: Booking):
    """
    Sends a WhatsApp alert when a booking is cancelled.

    Triggered by:
        - booking_service.process_email() on cancellation emails
        - manual_booking.cancel_booking() from dashboard
    """
    property_name = booking.property.name if booking.property else "Unknown Property"

    checkin  = booking.checkin_date.strftime("%b %d")
    checkout = booking.checkout_date.strftime("%b %d")
    nights   = (booking.checkout_date - booking.checkin_date).days

    message = f"""❌ *CANCELLED — {booking.platform.capitalize()}*

🏠 {property_name}
👤 {booking.guest_name or 'N/A'}
📅 {checkin} → {checkout}  ({nights} nights)

🔖 {booking.booking_id}"""

    result = _send_whatsapp_message(message)

    _log_notification(
        db=db,
        booking_id=booking.id,
        notification_type="cancellation",
        delivery_status="delivered" if "messages" in result else "failed",
        response_payload=result,
    )


# ─────────────────────────────────────────────
# 3. TOMORROW CLEANING REMINDER  (8PM IST)
# ─────────────────────────────────────────────

def send_tomorrow_cleanings(db: Session):
    """
    Finds all confirmed bookings checking out tomorrow.
    Sends one consolidated WhatsApp message.
    Scheduled at 8:00 PM IST every day by notification_worker.
    """
    tomorrow = date.today() + timedelta(days=1)

    bookings = (
        db.query(Booking)
        .join(Property)
        .filter(
            Booking.checkout_date == tomorrow,
            Booking.status == BookingStatus.confirmed,
        )
        .order_by(Property.name)
        .all()
    )

    if not bookings:
        print(f"[Scheduler] No checkouts tomorrow ({tomorrow}) — skipping.")
        return

    count = len(bookings)
    lines = "\n".join(f"  {i+1}. {b.property.name}" for i, b in enumerate(bookings))

    message = f"""🧹 *{count} CLEANING{'S' if count > 1 else ''} TOMORROW · {tomorrow.strftime('%b %d')}*

{lines}"""

    result = _send_whatsapp_message(message)
    status = "delivered" if "messages" in result else "failed"

    for booking in bookings:
        _log_notification(
            db=db,
            booking_id=booking.id,
            notification_type="tomorrow_cleaning",
            delivery_status=status,
            response_payload=result,
        )

    print(f"[Scheduler] Tomorrow cleanings sent — {len(bookings)} properties.")


# ─────────────────────────────────────────────
# 4. 20-DAY CLEANING SCHEDULE  (6AM IST)
# ─────────────────────────────────────────────

def send_upcoming_cleanings(db: Session):
    """
    Finds all confirmed bookings checking out within next 20 days.
    Sends a rolling schedule as one WhatsApp message.
    Scheduled at 6:00 AM IST every day by notification_worker.
    """
    today = date.today()
    window_end = today + timedelta(days=20)

    bookings = (
        db.query(Booking)
        .join(Property)
        .filter(
            Booking.checkout_date >= today,
            Booking.checkout_date <= window_end,
            Booking.status == BookingStatus.confirmed,
        )
        .order_by(Booking.checkout_date.asc())
        .all()
    )

    if not bookings:
        print(f"[Scheduler] No cleanings in next 20 days — skipping.")
        return

    count = len(bookings)
    lines = "\n".join(
        f"  {b.checkout_date.strftime('%b %d')}  {b.property.name}"
        for b in bookings
    )

    message = f"""📅 *NEXT 20 DAYS — {count} cleaning{'s' if count > 1 else ''}*

{lines}"""

    result = _send_whatsapp_message(message)
    status = "delivered" if "messages" in result else "failed"

    for booking in bookings:
        _log_notification(
            db=db,
            booking_id=booking.id,
            notification_type="upcoming_cleaning",
            delivery_status=status,
            response_payload=result,
        )

    print(f"[Scheduler] 20-day schedule sent — {len(bookings)} bookings.")