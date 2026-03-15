"""
manual_booking.py

Dashboard manual entry routes.
Notifications are triggered after every DB write — same as email-sourced bookings.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.db.database import get_db
from app.db.models import Booking, Property, BookingStatus
from app.db import crud
from app.services.notification_service import notify_new_booking, notify_cancellation

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def booking_to_dict(booking: Booking) -> dict:
    return {
        "booking_id": booking.booking_id,
        "guest":      booking.guest_name,
        "property":   booking.property.name if booking.property else "",
        "platform":   booking.platform,
        "checkin":    str(booking.checkin_date)  if booking.checkin_date  else "",
        "checkout":   str(booking.checkout_date) if booking.checkout_date else "",
        "status":     booking.status.value,
    }


# ── POST /api/manual-booking  (Add) ───────────────────────────────────────────

@router.post("/manual-booking")
def create_manual_booking(data: dict, db: Session = Depends(get_db)):
    # Duplicate check
    if db.query(Booking).filter(Booking.booking_id == data["booking_id"]).first():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Booking ID '{data['booking_id']}' already exists."}
        )

    property_obj = crud.get_or_create_property(db=db, property_name=data["property_name"])

    booking = Booking(
        booking_id=data["booking_id"],
        platform=data["platform"],
        property_id=property_obj.id,
        guest_name=data["guest_name"],
        checkin_date=parse_date(data.get("checkin_date")),
        checkout_date=parse_date(data.get("checkout_date")),
        status=BookingStatus(data.get("status", "confirmed")),
    )

    try:
        db.add(booking)
        db.commit()
        db.refresh(booking)  # loads booking.property relationship before notify

        # ── Notify: same path as email-sourced bookings ───────────────
        notify_new_booking(db=db, booking=booking)

        return {"success": True}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# ── POST /api/lookup-booking  (used by Cancel & Update drawers) ───────────────

@router.post("/lookup-booking")
def lookup_booking(data: dict, db: Session = Depends(get_db)):
    booking_id = (data.get("booking_id") or "").strip()
    if not booking_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "booking_id is required."})

    booking = (
        db.query(Booking)
        .join(Property)
        .filter(Booking.booking_id == booking_id)
        .first()
    )

    if not booking:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"No booking found with ID '{booking_id}'."}
        )

    return {"success": True, "booking": booking_to_dict(booking)}


# ── POST /api/cancel-booking ──────────────────────────────────────────────────

@router.post("/cancel-booking")
def cancel_booking(data: dict, db: Session = Depends(get_db)):
    booking_id = (data.get("booking_id") or "").strip()
    if not booking_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "booking_id is required."})

    booking = (
        db.query(Booking)
        .join(Property)
        .filter(Booking.booking_id == booking_id)
        .first()
    )

    if not booking:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"No booking found with ID '{booking_id}'."}
        )

    if booking.status == BookingStatus.cancelled:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "This booking is already cancelled."}
        )

    try:
        booking.status = BookingStatus.cancelled
        db.commit()
        db.refresh(booking)  # loads booking.property relationship before notify

        # ── Notify: same path as email-sourced cancellations ──────────
        notify_cancellation(db=db, booking=booking)

        return {"success": True}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# ── POST /api/update-booking ──────────────────────────────────────────────────

@router.post("/update-booking")
def update_booking(data: dict, db: Session = Depends(get_db)):
    """
    Updates booking fields from dashboard.
    No notification on updates — only on new bookings and cancellations.
    Add notify_modification() here in future if needed.
    """
    booking_id = (data.get("booking_id") or "").strip()
    if not booking_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "booking_id is required."})

    booking = (
        db.query(Booking)
        .join(Property)
        .filter(Booking.booking_id == booking_id)
        .first()
    )

    if not booking:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"No booking found with ID '{booking_id}'."}
        )

    try:
        if data.get("property_name"):
            prop = crud.get_or_create_property(db=db, property_name=data["property_name"])
            booking.property_id = prop.id

        if data.get("guest_name"):
            booking.guest_name = data["guest_name"]

        if data.get("checkin_date"):
            booking.checkin_date = parse_date(data["checkin_date"])

        if data.get("checkout_date"):
            booking.checkout_date = parse_date(data["checkout_date"])

        if data.get("status"):
            booking.status = BookingStatus(data["status"])

        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})