from dotenv import load_dotenv
load_dotenv()

import time
import logging
import sys

from app.integrations.gmail_client import fetch_booking_emails, mark_email_as_read
from app.services.booking_service import process_email, store_failed_email, EmailAlreadyProcessed
from app.db.database import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60
BACKOFF_STEPS = [60, 120, 300]


def _process_single_email(email: dict) -> None:
    message_id = email["message_id"]
    body = email["body"]
    service = email["_service"]

    db = SessionLocal()
    try:
        process_email(db, body, message_id)
        mark_email_as_read(service, message_id)
        logger.info("Email %s processed and marked as read.", message_id)

    except EmailAlreadyProcessed:
        logger.warning("Email %s already processed, skipping.", message_id)
        mark_email_as_read(service, message_id)

    except Exception as e:
        logger.error("Failed to process email %s: %s", message_id, e)
        try:
            store_failed_email(db, message_id, body, str(e))
            logger.info("Email %s saved to failed_emails for retry.", message_id)
        except Exception as store_err:
            logger.error(
                "Could not save email %s to failed_emails: %s",
                message_id, store_err
            )

    finally:
        db.close()


def run_worker():
    logger.info("Email worker started.")
    consecutive_failures = 0

    while True:
        logger.info("Polling Gmail for new booking emails...")

        try:
            emails = fetch_booking_emails()
            logger.info("Found %d unread booking email(s) to process.", len(emails))

            for email in emails:
                _process_single_email(email)

            consecutive_failures = 0

        except RuntimeError as e:
            logger.critical(
                "Gmail authentication failed — worker is stopping. Error: %s", e
            )
            sys.exit(1)

        except Exception as e:
            consecutive_failures += 1
            backoff = BACKOFF_STEPS[min(consecutive_failures - 1, len(BACKOFF_STEPS) - 1)]
            logger.error(
                "Gmail fetch failed (attempt %d): %s — retrying in %ds.",
                consecutive_failures, e, backoff
            )
            time.sleep(backoff)
            continue

        time.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Worker shut down cleanly.")


if __name__ == "__main__":
    run_worker()