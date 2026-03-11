import logging

from app.integrations.gmail_client import fetch_booking_emails, mark_email_read
from app.services.booking_service import process_email
from app.db.database import SessionLocal
from app.services.booking_service import EmailAlreadyProcessed
from app.services.booking_service import store_failed_email


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_worker():

    logger.info("Email worker started")

    db = SessionLocal()

    try:

        emails = fetch_booking_emails()

        logger.info(f"{len(emails)} unread emails fetched")

        for email in emails:

            message_id = email["message_id"]

            try:

                logger.info(f"Processing email {message_id}")

                process_email(
                    db,
                    email["body"],
                    message_id
                )

                mark_email_read(message_id)

            except EmailAlreadyProcessed:

                logger.info(f"Skipping already processed email {message_id}")

                mark_email_read(message_id)

            except Exception as e:

                logger.error(f"Failed email {message_id}: {str(e)}")

                store_failed_email(
                    db,
                    message_id,
                    email["body"],
                    str(e)
                )

    finally:
        db.close()


if __name__ == "__main__":
    run_worker()