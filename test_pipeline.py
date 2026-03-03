import uuid
from pathlib import Path

from app.db.database import SessionLocal
from app.services.booking_service import process_email, EmailAlreadyProcessed


def load_email_file(filepath: str) -> str:
    return Path(filepath).read_text(encoding="utf-8")


def run_test(email_path: str):
    db = SessionLocal()

    try:
        email_text = load_email_file(email_path)

        # Simulate Gmail message_id
        message_id = str(uuid.uuid4())

        booking = process_email(
            db=db,
            email_text=email_text,
            message_id=message_id,
        )

        print("✅ Booking processed successfully!")
        print(f"ID: {booking.id}")
        print(f"Booking ID: {booking.booking_id}")
        print(f"Platform: {booking.platform}")
        print(f"Guest: {booking.guest_name}")
        print(f"Check-in: {booking.checkin_date}")
        print(f"Check-out: {booking.checkout_date}")
        print(f"Status: {booking.status}")

    except EmailAlreadyProcessed as e:
        print("⚠️ Email already processed:", e)

    except Exception as e:
        print("❌ Error:", e)

    finally:
        db.close()


if __name__ == "__main__":
    print("Running Airbnb test...\n")
    run_test("sample_airbnb.txt")

    print("\nRunning Vrbo test...\n")
    run_test("sample_vrbo_two.txt")