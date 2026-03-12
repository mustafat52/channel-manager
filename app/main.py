from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy import Enum as SAEnum
from starlette.middleware.sessions import SessionMiddleware
from datetime import date, timedelta

from app.db.database import SessionLocal
from app.db.models import Booking, Property, BookingStatus  # make sure BookingStatus is imported
from app.api import auth

from app.api.manual_booking import router as manual_booking_router


app = FastAPI()
app.include_router(manual_booking_router, prefix="/api")
app.add_middleware(SessionMiddleware, secret_key="change-this-secret-key")

templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router)


@app.get("/")
def home():
    return RedirectResponse("/login")


# ── Single, correct /dashboard route ──────────────────────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    platform: str = None,
    status: str = None,
    window: int | None = None,       # default 20-day checkout window
    search: str = None,
):
    if not request.session.get("user"):
        return RedirectResponse(url="/login")

    db: Session = SessionLocal()

    try:
        today = date.today()

        query = db.query(Booking).join(Property)

        # PLATFORM FILTER
        if platform:
            query = query.filter(Booking.platform == platform)

        # STATUS FILTER
        if status:
            try:
                query = query.filter(Booking.status == BookingStatus(status))
            except ValueError:
                pass

        # CHECKOUT WINDOW FILTER
        if window is not None:
            window_end = today + timedelta(days=window)

            query = query.filter(
                Booking.checkout_date >= today,
                Booking.checkout_date <= window_end,
            )

        # SEARCH FILTER
        if search:
            query = query.filter(
                or_(
                    Booking.guest_name.ilike(f"%{search}%"),
                    Booking.booking_id.ilike(f"%{search}%"),
                    Property.name.ilike(f"%{search}%"),
                )
            )

        bookings = query.order_by(Booking.checkout_date.asc()).all()

        # ── Stats (global, unaffected by active filters) ──────────────────────
        total_bookings   = db.query(func.count(Booking.id)).scalar()
        airbnb_count     = db.query(func.count(Booking.id)).filter(Booking.platform == "airbnb").scalar()
        vrbo_count       = db.query(func.count(Booking.id)).filter(Booking.platform == "vrbo").scalar()
        booking_count    = db.query(func.count(Booking.id)).filter(Booking.platform == "booking").scalar()
        confirmed_count  = db.query(func.count(Booking.id)).filter(Booking.status == BookingStatus("confirmed")).scalar()

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "bookings": bookings,

                # stats
                "total_bookings":  total_bookings,
                "airbnb_count":    airbnb_count,
                "vrbo_count":      vrbo_count,
                "booking_count":   booking_count,
                "confirmed_count": confirmed_count,

                # active filter state — None means "not selected"
                "selected_platform": platform,
                "selected_status":   status,
                "window":            window,
                "search":            search,
            },
        )

    finally:
        db.close()