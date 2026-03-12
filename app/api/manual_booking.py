from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.database import get_db
from app.db.models import Booking, BookingStatus
from app.db import crud

router = APIRouter()


@router.post("/manual-booking")
def create_manual_booking(data: dict, db: Session = Depends(get_db)):

    # Get or create property
    property_obj = crud.get_or_create_property(
        db=db,
        property_name=data["property_name"]
    )

    booking = Booking(
        booking_id=data["booking_id"],
        platform=data["platform"],
        property_id=property_obj.id,
        guest_name=data["guest_name"],
        checkin_date=datetime.strptime(data["checkin_date"], "%Y-%m-%d").date(),
        checkout_date=datetime.strptime(data["checkout_date"], "%Y-%m-%d").date(),
        status=BookingStatus(data["status"])
    )

    db.add(booking)
    db.commit()

    return {"success": True}