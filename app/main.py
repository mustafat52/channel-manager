from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from starlette.middleware.sessions import SessionMiddleware
from datetime import date, timedelta

from app.db.database import SessionLocal
from app.db.models import Booking, Property, BookingStatus
from app.api import auth
from app.api.manual_booking import router as manual_booking_router
from app.workers.notification_worker import create_scheduler


app = FastAPI()
app.include_router(manual_booking_router, prefix="/api")
app.add_middleware(SessionMiddleware, secret_key="change-this-secret-key")

templates = Jinja2Templates(directory="app/templates")
app.include_router(auth.router)


# ── Scheduler lifecycle ────────────────────────────────────────────────────────

@app.on_event("startup")
def start_scheduler():
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    print("[Scheduler] Started — 6AM IST (20-day schedule) · 8PM IST (tomorrow reminder)")


@app.on_event("shutdown")
def stop_scheduler():
    app.state.scheduler.shutdown(wait=False)
    print("[Scheduler] Stopped.")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return RedirectResponse("/login")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    platform: str = None,
    status: str = None,
    window: str = None,
    search: str = None,
):
    if not request.session.get("user"):
        return RedirectResponse(url="/login")

    window_int: int | None = None
    if window is not None and window.strip().lstrip('-').isdigit():
        window_int = int(window)

    db: Session = SessionLocal()

    try:
        today = date.today()
        query = db.query(Booking).join(Property)

        if platform:
            query = query.filter(Booking.platform == platform)

        if status:
            try:
                query = query.filter(Booking.status == BookingStatus(status))
            except ValueError:
                pass

        if window_int is not None:
            window_end = today + timedelta(days=window_int)
            query = query.filter(
                Booking.checkout_date >= today,
                Booking.checkout_date <= window_end,
            )

        if search:
            query = query.filter(
                or_(
                    Booking.guest_name.ilike(f"%{search}%"),
                    Booking.booking_id.ilike(f"%{search}%"),
                    Property.name.ilike(f"%{search}%"),
                )
            )

        bookings = query.order_by(Booking.checkout_date.asc()).all()

        total_bookings  = db.query(func.count(Booking.id)).scalar()
        airbnb_count    = db.query(func.count(Booking.id)).filter(Booking.platform == "airbnb").scalar()
        vrbo_count      = db.query(func.count(Booking.id)).filter(Booking.platform == "vrbo").scalar()
        booking_count   = db.query(func.count(Booking.id)).filter(Booking.platform == "booking").scalar()
        confirmed_count = db.query(func.count(Booking.id)).filter(Booking.status == BookingStatus("confirmed")).scalar()

        # Active properties — drives Add/Update drawer dropdowns
        properties = db.query(Property).filter(Property.is_active == True).order_by(Property.name).all()

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request":           request,
                "bookings":          bookings,
                "total_bookings":    total_bookings,
                "airbnb_count":      airbnb_count,
                "vrbo_count":        vrbo_count,
                "booking_count":     booking_count,
                "confirmed_count":   confirmed_count,
                "selected_platform": platform,
                "selected_status":   status,
                "window":            window_int,
                "search":            search,
                "properties":        properties,
            },
        )

    finally:
        db.close()