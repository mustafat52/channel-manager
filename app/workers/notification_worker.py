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
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from app.db.database import SessionLocal
from app.services.notification_service import (
    send_upcoming_cleanings,
    send_tomorrow_cleanings,
)
from app.integrations.gmail_client import fetch_booking_emails
from app.workers.email_worker import _process_single_email

import logging
logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


# ─────────────────────────────────────────────
# JOB WRAPPERS
# Each opens and closes its own DB session cleanly.
# ─────────────────────────────────────────────

def job_upcoming_cleanings():
    """6:00 AM IST — 20-day cleaning schedule."""
    logger.info("Running: send_upcoming_cleanings")
    db = SessionLocal()
    try:
        send_upcoming_cleanings(db)
    except Exception as e:
        logger.error("Error in send_upcoming_cleanings: %s", e)
    finally:
        db.close()


def job_tomorrow_cleanings():
    """8:00 PM IST — tomorrow's cleaning reminder."""
    logger.info("Running: send_tomorrow_cleanings")
    db = SessionLocal()
    try:
        send_tomorrow_cleanings(db)
    except Exception as e:
        logger.error("Error in send_tomorrow_cleanings: %s", e)
    finally:
        db.close()


def job_email_poll():
    """Every 60 seconds — poll Gmail for new booking emails."""
    logger.info("Running: email poll")
    try:
        emails = fetch_booking_emails()
        if emails:
            logger.info("Found %d email(s) to process.", len(emails))
        for email in emails:
            _process_single_email(email)
    except RuntimeError as e:
        # OAuth token expired — needs manual re-auth
        logger.critical("Gmail auth failed — email polling stopped: %s", e)
    except Exception as e:
        logger.error("Email poll error: %s", e)


# ─────────────────────────────────────────────
# SCHEDULER FACTORY
# Called once on FastAPI startup in main.py
# ─────────────────────────────────────────────

def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)

    # 6:00 AM IST — 20-day rolling schedule
    scheduler.add_job(
        job_upcoming_cleanings,
        trigger=CronTrigger(hour=6, minute=0, timezone=IST),
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

    # Every 60 seconds — Gmail email polling
    scheduler.add_job(
        job_email_poll,
        trigger=IntervalTrigger(seconds=60),
        id="email_poll",
        name="Gmail email poller",
        replace_existing=True,
    )

    return scheduler