from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from starlette.middleware.sessions import SessionMiddleware
from datetime import date, timedelta
import os
from app.db.database import SessionLocal
from app.db.models import Booking, Property, BookingStatus
from app.api import auth
from app.api.manual_booking import router as manual_booking_router
from app.workers.notification_worker import create_scheduler


app = FastAPI()
app.include_router(manual_booking_router, prefix="/api")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "change-this-secret-key"))

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
        properties = db.query(Property).filter(Property.is_active == True).order_by(Property.name).all()

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request":          request,
                "bookings":         bookings,
                "total_bookings":   total_bookings,
                "airbnb_count":     airbnb_count,
                "vrbo_count":       vrbo_count,
                "booking_count":    booking_count,
                "confirmed_count":  confirmed_count,
                "selected_platform": platform,
                "selected_status":   status,
                "window":            window_int,
                "search":            search,
                "properties":        properties,
            },
        )

    finally:
        db.close()

# ── Analytics route ────────────────────────────────────────────────────────────

from collections import defaultdict
from datetime import date as dt_date
from calendar import month_abbr

@app.get("/analytics", response_class=HTMLResponse)
def analytics(request: Request):
    if not request.session.get("user"):
        return RedirectResponse(url="/login")

    db: Session = SessionLocal()

    try:
        all_bookings = db.query(Booking).join(Property).all()
        total = len(all_bookings)

        def _count(platform=None, status=None):
            q = db.query(func.count(Booking.id))
            if platform: q = q.filter(Booking.platform == platform)
            if status:   q = q.filter(Booking.status == BookingStatus(status))
            return q.scalar() or 0

        airbnb_count  = _count("airbnb")
        vrbo_count    = _count("vrbo")
        booking_count = _count("booking")

        confirmed = _count(status="confirmed")
        cancelled = _count(status="cancelled")

        confirmed_pct = round(confirmed / total * 100) if total else 0
        cancelled_pct = round(cancelled / total * 100) if total else 0

        platform_counts = {"airbnb": airbnb_count, "vrbo": vrbo_count, "booking": booking_count}
        top_platform_key = max(platform_counts, key=platform_counts.get)
        top_platform_labels = {"airbnb": "Airbnb", "vrbo": "Vrbo", "booking": "Booking.com"}
        top_platform = top_platform_labels[top_platform_key]
        top_platform_pct = round(platform_counts[top_platform_key] / total * 100) if total else 0

        # Status breakdown per platform
        def _pstatus(platform, status):
            return _count(platform, status)

        airbnb_confirmed  = _pstatus("airbnb",  "confirmed")
        airbnb_cancelled  = _pstatus("airbnb",  "cancelled")
        airbnb_modified   = _pstatus("airbnb",  "modified")
        vrbo_confirmed    = _pstatus("vrbo",     "confirmed")
        vrbo_cancelled    = _pstatus("vrbo",     "cancelled")
        vrbo_modified     = _pstatus("vrbo",     "modified")
        booking_confirmed = _pstatus("booking",  "confirmed")
        booking_cancelled = _pstatus("booking",  "cancelled")
        booking_modified  = _pstatus("booking",  "modified")

        # Cancellation rate per platform
        def _cancel_pct(total_p, cancelled_p):
            return round(cancelled_p / total_p * 100) if total_p else 0

        airbnb_cancel_pct  = _cancel_pct(airbnb_count,  airbnb_cancelled)
        vrbo_cancel_pct    = _cancel_pct(vrbo_count,    vrbo_cancelled)
        booking_cancel_pct = _cancel_pct(booking_count, booking_cancelled)

        # Monthly trend — last 6 months
        today = dt_date.today()
        months = []
        for i in range(5, -1, -1):
            m = (today.month - i - 1) % 12 + 1
            y = today.year - ((today.month - i - 1) // 12)
            months.append((y, m))

        trend_labels  = [month_abbr[m] for _, m in months]
        trend_airbnb  = []
        trend_vrbo    = []
        trend_booking = []

        for y, m in months:
            def _monthly(platform, yr, mo):
                return db.query(func.count(Booking.id)).filter(
                    Booking.platform == platform,
                    func.extract("year",  Booking.created_at) == yr,
                    func.extract("month", Booking.created_at) == mo,
                ).scalar() or 0

            trend_airbnb.append(_monthly("airbnb",  y, m))
            trend_vrbo.append(  _monthly("vrbo",    y, m))
            trend_booking.append(_monthly("booking", y, m))

        # Top properties by booking count
        from sqlalchemy import desc
        prop_rows = (
            db.query(Property.name, func.count(Booking.id).label("cnt"))
            .join(Booking, Booking.property_id == Property.id)
            .group_by(Property.name)
            .order_by(desc("cnt"))
            .limit(7)
            .all()
        )
        property_labels = [r.name for r in prop_rows]
        property_counts = [r.cnt  for r in prop_rows]


        return templates.TemplateResponse(
            "analytics.html",
            {
                "request": request,
                "total": total,
                "confirmed": confirmed,
                "cancelled": cancelled,
                "confirmed_pct": confirmed_pct,
                "cancelled_pct": cancelled_pct,
                "top_platform": top_platform,
                "top_platform_pct": top_platform_pct,
                "airbnb_count":  airbnb_count,
                "vrbo_count":    vrbo_count,
                "booking_count": booking_count,
                "airbnb_confirmed":  airbnb_confirmed,
                "airbnb_cancelled":  airbnb_cancelled,
                "airbnb_modified":   airbnb_modified,
                "vrbo_confirmed":    vrbo_confirmed,
                "vrbo_cancelled":    vrbo_cancelled,
                "vrbo_modified":     vrbo_modified,
                "booking_confirmed": booking_confirmed,
                "booking_cancelled": booking_cancelled,
                "booking_modified":  booking_modified,
                "airbnb_cancel_pct":  airbnb_cancel_pct,
                "vrbo_cancel_pct":    vrbo_cancel_pct,
                "booking_cancel_pct": booking_cancel_pct,
                "trend_labels":   trend_labels,
                "trend_airbnb":   trend_airbnb,
                "trend_vrbo":     trend_vrbo,
                "trend_booking":  trend_booking,
                "property_labels": property_labels,
                "property_counts": property_counts,
            },
        )

    finally:
        db.close()