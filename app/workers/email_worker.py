import time

from app.integrations.gmail_client import fetch_booking_emails
from app.services.booking_service import process_email
from app.db.database import SessionLocal
from app.services.booking_service import EmailAlreadyProcessed


def run_worker():

    while True:

        print("Worker running... checking Gmail")

        db = SessionLocal()

        try:

            emails = fetch_booking_emails()
            print("Worker running... checking Gmail")

            for email in emails:
                print("Processing email:", email["message_id"])
                print(email["body"][:200])

                try:
                    process_email(
                        db,
                        email["body"],
                        email["message_id"]
                    )

                except EmailAlreadyProcessed:
                    print(f"Skipping already processed email {email['message_id']}")

                except Exception as e:
                    print(f"Skipping unsupported email {email['message_id']}: {e}")    

        finally:
            db.close()

        time.sleep(60)


if __name__ == "__main__":
    run_worker()