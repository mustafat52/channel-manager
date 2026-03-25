from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from starlette.middleware.sessions import SessionMiddleware
from datetime import date, timedelta, datetime


import os

import logging
logger = logging.getLogger(__name__)

# Warn loudly if TEST_MODE is on at startup
if os.getenv("TEST_MODE", "false").lower() == "true":
    logger.warning("TEST_MODE is ON — Gmail sender allowlist is disabled. Set TEST_MODE=false on Railway.")



from app.db.database import SessionLocal
from app.db.models import Booking, Property, BookingStatus
from app.api import auth
from app.api.manual_booking import router as manual_booking_router
from app.workers.notification_worker import create_scheduler


app = FastAPI()
app.include_router(manual_booking_router, prefix="/api")

_session_secret = os.environ.get("SECRET_KEY")
if not _session_secret:
    raise RuntimeError("SECRET_KEY is not set in environment variables.")
app.add_middleware(SessionMiddleware, secret_key=_session_secret)

templates = Jinja2Templates(directory="app/templates")
app.include_router(auth.router)


# ── Scheduler lifecycle ────────────────────────────────────────────────────────

@app.on_event("startup")
def start_scheduler():
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started — 6AM IST (20-day schedule) · 8PM IST (tomorrow reminder)")

@app.on_event("shutdown")
def stop_scheduler():
    try:
        app.state.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    except Exception:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return RedirectResponse("/login")

def format_us(date_obj):
    if not date_obj:
        return ""
    if isinstance(date_obj, str):
        date_obj = datetime.fromisoformat(date_obj)
    return date_obj.strftime("%m/%d/%Y")


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
    window_type: str | None = None

    if window:
        w = window.strip().lower()

        if w.isdigit():
            window_int = int(w)
        elif w in ["today", "tomorrow"]:
            window_type = w

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

        # ✅ TODAY / TOMORROW filters
        if window_type == "today":
            query = query.filter(Booking.checkout_date == today)

        elif window_type == "tomorrow":
            query = query.filter(Booking.checkout_date == today + timedelta(days=1))

        # ✅ EXISTING WINDOW FILTER (3,7,14...)
        elif window_int is not None:
            window_end = today + timedelta(days=window_int)
            query = query.filter(
                Booking.checkout_date >= today,
                Booking.checkout_date <= window_end,
            )

        if search:
            search = search[:100]
            query = query.filter(
                or_(
                    Booking.guest_name.ilike(f"%{search}%"),
                    Booking.booking_id.ilike(f"%{search}%"),
                    Property.name.ilike(f"%{search}%"),
                )
            )

        bookings = query.order_by(Booking.checkout_date.asc()).all()
        
        for b in bookings:
            b.checkin_date = format_us(b.checkin_date)
            b.checkout_date = format_us(b.checkout_date)

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
                "window":            window if window else None,
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
        today = dt_date.today()

        # ── 1. Total count ────────────────────────────────────────────
        total = db.query(func.count(Booking.id)).scalar() or 0

        # ── 2. All platform+status combos in ONE query ────────────────
        rows = (
            db.query(
                Booking.platform,
                Booking.status,
                func.count(Booking.id).label("cnt"),
            )
            .group_by(Booking.platform, Booking.status)
            .all()
        )

        # Build lookup: counts[(platform, status)] = count
        counts = {}
        for row in rows:
            counts[(row.platform, row.status.value)] = row.cnt

        def _c(platform, status):
            return counts.get((platform, status), 0)

        airbnb_count  = sum(v for (p, s), v in counts.items() if p == "airbnb")
        vrbo_count    = sum(v for (p, s), v in counts.items() if p == "vrbo")
        booking_count = sum(v for (p, s), v in counts.items() if p == "booking")

        confirmed = sum(v for (p, s), v in counts.items() if s == "confirmed")
        cancelled = sum(v for (p, s), v in counts.items() if s == "cancelled")

        confirmed_pct = round(confirmed / total * 100) if total else 0
        cancelled_pct = round(cancelled / total * 100) if total else 0

        platform_counts = {"airbnb": airbnb_count, "vrbo": vrbo_count, "booking": booking_count}
        top_platform_key = max(platform_counts, key=platform_counts.get) if total else "airbnb"
        top_platform_labels = {"airbnb": "Airbnb", "vrbo": "Vrbo", "booking": "Booking.com"}
        top_platform = top_platform_labels[top_platform_key]
        top_platform_pct = round(platform_counts[top_platform_key] / total * 100) if total else 0

        airbnb_confirmed  = _c("airbnb",  "confirmed")
        airbnb_cancelled  = _c("airbnb",  "cancelled")
        airbnb_modified   = _c("airbnb",  "modified")
        vrbo_confirmed    = _c("vrbo",    "confirmed")
        vrbo_cancelled    = _c("vrbo",    "cancelled")
        vrbo_modified     = _c("vrbo",    "modified")
        booking_confirmed = _c("booking", "confirmed")
        booking_cancelled = _c("booking", "cancelled")
        booking_modified  = _c("booking", "modified")

        def _cancel_pct(total_p, cancelled_p):
            return round(cancelled_p / total_p * 100) if total_p else 0

        airbnb_cancel_pct  = _cancel_pct(airbnb_count,  airbnb_cancelled)
        vrbo_cancel_pct    = _cancel_pct(vrbo_count,    vrbo_cancelled)
        booking_cancel_pct = _cancel_pct(booking_count, booking_cancelled)

        # ── 3. Monthly trend — ONE query ──────────────────────────────
        months = []
        for i in range(5, -1, -1):
            m = (today.month - i - 1) % 12 + 1
            y = today.year - ((today.month - i - 1) // 12)
            months.append((y, m))

        trend_rows = (
            db.query(
                Booking.platform,
                func.extract("year",  Booking.created_at).label("yr"),
                func.extract("month", Booking.created_at).label("mo"),
                func.count(Booking.id).label("cnt"),
            )
            .filter(
                func.extract("year",  Booking.created_at) >= months[0][0],
                func.extract("month", Booking.created_at) >= 1,
            )
            .group_by(
                Booking.platform,
                func.extract("year",  Booking.created_at),
                func.extract("month", Booking.created_at),
            )
            .all()
        )

        # Build trend lookup: trend[(platform, year, month)] = count
        trend_lookup = {}
        for row in trend_rows:
            trend_lookup[(row.platform, int(row.yr), int(row.mo))] = row.cnt

        trend_labels  = [month_abbr[m] for _, m in months]
        trend_airbnb  = [trend_lookup.get(("airbnb",  y, m), 0) for y, m in months]
        trend_vrbo    = [trend_lookup.get(("vrbo",    y, m), 0) for y, m in months]
        trend_booking = [trend_lookup.get(("booking", y, m), 0) for y, m in months]

        # ── 4. Top properties — ONE query ─────────────────────────────
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