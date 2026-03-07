from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from starlette.middleware.sessions import SessionMiddleware

from app.db.database import SessionLocal
from app.db.models import Booking, Property
from app.api import auth


app = FastAPI()

# Session middleware for login sessions
app.add_middleware(SessionMiddleware, secret_key="change-this-secret-key")

templates = Jinja2Templates(directory="app/templates")

# include auth routes (login)
app.include_router(auth.router)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, platform: str = None):

    # check if user is logged in
    if not request.session.get("user"):
        return RedirectResponse(url="/login")

    db: Session = SessionLocal()

    try:
        query = db.query(Booking).join(Property)

        if platform:
            query = query.filter(Booking.platform == platform)

        bookings = query.order_by(Booking.created_at.desc()).all()

        total_bookings = db.query(func.count(Booking.id)).scalar()
        airbnb_count = (
            db.query(func.count(Booking.id))
            .filter(Booking.platform == "airbnb")
            .scalar()
        )

        vrbo_count = (
            db.query(func.count(Booking.id))
            .filter(Booking.platform == "vrbo")
            .scalar()
        )

        confirmed_count = (
            db.query(func.count(Booking.id))
            .filter(Booking.status == "confirmed")
            .scalar()
        )

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

@app.get("/")
def home():
    return RedirectResponse("/login")        