"""
notification_worker.py
Location: app/workers/notification_worker.py

Scheduled notification jobs using APScheduler.
Registered on FastAPI startup in main.py.

Jobs:
    6:00 AM IST  →  send_upcoming_cleanings  (20-day rolling schedule)
    8:00 PM IST  →  send_tomorrow_cleanings  (next-day cleaning reminder)
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.db.database import SessionLocal
from app.services.notification_service import (
    send_upcoming_cleanings,
    send_tomorrow_cleanings,
)

IST = pytz.timezone("Asia/Kolkata")


# ─────────────────────────────────────────────
# JOB WRAPPERS
# Each opens and closes its own DB session cleanly.
# ─────────────────────────────────────────────

def job_upcoming_cleanings():
    """6:00 AM IST — 20-day cleaning schedule."""
    print("[Scheduler] Running: send_upcoming_cleanings")
    db = SessionLocal()
    try:
        send_upcoming_cleanings(db)
    except Exception as e:
        print(f"[Scheduler] Error in send_upcoming_cleanings: {e}")
    finally:
        db.close()


def job_tomorrow_cleanings():
    """8:00 PM IST — tomorrow's cleaning reminder."""
    print("[Scheduler] Running: send_tomorrow_cleanings")
    db = SessionLocal()
    try:
        send_tomorrow_cleanings(db)
    except Exception as e:
        print(f"[Scheduler] Error in send_tomorrow_cleanings: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────
# SCHEDULER FACTORY
# Called once on FastAPI startup in main.py
# ─────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)

    # 6:00 AM IST — 20-day rolling schedule
    scheduler.add_job(
        job_upcoming_cleanings,
        trigger=CronTrigger(hour=8, minute=15, timezone=IST),
        id="upcoming_cleanings",
        name="20-day cleaning schedule",
        replace_existing=True,
    )

    # 8:00 PM IST — tomorrow reminder
    scheduler.add_job(
        job_tomorrow_cleanings,
        trigger=CronTrigger(hour=20, minute=0, timezone=IST),
        id="tomorrow_cleanings",
        name="Tomorrow cleaning reminder",
        replace_existing=True,
    )

    return scheduler