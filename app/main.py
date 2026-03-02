from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import Booking, Property

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, platform: str = None):
    db: Session = SessionLocal()

    try:
        query = db.query(Booking).join(Property)

        # Platform filter
        if platform:
            query = query.filter(Booking.platform == platform)

        bookings = query.order_by(Booking.created_at.desc()).all()

        # Stats
        total_bookings = db.query(func.count(Booking.id)).scalar()
        airbnb_count = db.query(func.count(Booking.id)).filter(Booking.platform == "airbnb").scalar()
        vrbo_count = db.query(func.count(Booking.id)).filter(Booking.platform == "vrbo").scalar()
        confirmed_count = db.query(func.count(Booking.id)).filter(Booking.status == "confirmed").scalar()

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "bookings": bookings,
                "total_bookings": total_bookings,
                "airbnb_count": airbnb_count,
                "vrbo_count": vrbo_count,
                "confirmed_count": confirmed_count,
                "selected_platform": platform,
            },
        )
    finally:
        db.close()