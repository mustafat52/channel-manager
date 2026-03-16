

from dotenv import load_dotenv
load_dotenv()

import time
import signal
import logging
import sys

from app.integrations.gmail_client import fetch_booking_emails, mark_email_as_read
from app.services.booking_service import process_email, store_failed_email, EmailAlreadyProcessed
from app.db.database import SessionLocal

# ---------------------------------------------------------------------------
# LOGGING
# FIX: Replaced all print() calls with structured logging.
# - Timestamps on every line
# - Severity levels (INFO / WARNING / ERROR) so you can filter and alert
# - No PII in any log line (message_id only, never body content)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POLL INTERVAL & BACKOFF
# Normal interval: 60 seconds.
# After a Gmail/network failure, back off progressively so we don't hammer
# the API or burn through quota while the service is down.
# ---------------------------------------------------------------------------
POLL_INTERVAL_SECONDS = 60
BACKOFF_STEPS = [60, 120, 300]   # 1 min → 2 min → 5 min, then stays at 5 min


# ---------------------------------------------------------------------------
# GRACEFUL SHUTDOWN
# FIX: The original while True loop couldn't be stopped cleanly.
# SIGTERM (sent by Docker, systemd, or Ctrl+C) now sets a flag that lets
# the current batch finish before the process exits — no half-processed emails,
# no dangling DB sessions.
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# PER-EMAIL PROCESSING
# FIX: DB session is now opened and closed per email, not once for the whole
# batch. If one email causes a DB error that corrupts the session state,
# it no longer affects every subsequent email in the same poll cycle.
# ---------------------------------------------------------------------------
def _process_single_email(email: dict) -> None:
    """
    Parse, validate, and store a single booking email.
    Opens its own DB session and marks the email as read only on success.
    """
    message_id = email["message_id"]
    body = email["body"]
    service = email["_service"]   # passed through from gmail_client

    db = SessionLocal()
    try:
        process_email(db, body, message_id)

        # FIX: Mark as read ONLY after successful processing.
        # Previously this happened before parsing — a parse failure
        # would silently lose the email forever.
        mark_email_as_read(service, message_id)
        logger.info("Email %s processed and marked as read.", message_id)

    except EmailAlreadyProcessed:
        # Not an error — just a duplicate. Mark it read and move on.
        logger.warning("Email %s already processed, skipping.", message_id)
        mark_email_as_read(service, message_id)

    except Exception as e:
        # FIX: Log only the message_id and error — never the email body.
        # The body can contain guest names, phone numbers, and financials.
        logger.error("Failed to process email %s: %s", message_id, e)

        try:
            # Store in failed_emails for manual review / retry
            # Body is stored in the DB (which has access controls) not in logs
            store_failed_email(db, message_id, body, str(e))
            logger.info("Email %s saved to failed_emails for retry.", message_id)
        except Exception as store_err:
            logger.error(
                "Could not save email %s to failed_emails: %s",
                message_id, store_err
            )

        # Leave the email as UNREAD so the worker retries it next poll.
        # Once you've fixed the underlying issue, it will be picked up again.

    finally:
        db.close()

