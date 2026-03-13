"""
test_pipeline.py
----------------
End-to-end tests that go through the full stack:
    sample email file → booking_service → database

Requires a live DB connection. Run from project root:
    python test_pipeline.py
"""

import uuid
from pathlib import Path

from app.db.database import SessionLocal
from app.services.booking_service import process_email, EmailAlreadyProcessed

from dotenv import load_dotenv
load_dotenv()

def load_email(filepath: str) -> str:
    return Path(filepath).read_text(encoding="utf-8")


def run_test(label: str, email_path: str):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")

    db = SessionLocal()
    try:
        email_text = load_email(email_path)
        message_id = str(uuid.uuid4())   # simulate a unique Gmail message ID

        booking = process_email(db=db, email_text=email_text, message_id=message_id)

        print("✅ Processed successfully!")
        print(f"   DB ID       : {booking.id}")
        print(f"   Booking ID  : {booking.booking_id}")
        print(f"   Platform    : {booking.platform}")
        print(f"   Guest       : {booking.guest_name}")
        print(f"   Check-in    : {booking.checkin_date}")
        print(f"   Check-out   : {booking.checkout_date}")
        print(f"   Status      : {booking.status}")

    except EmailAlreadyProcessed as e:
        print(f"⚠️  Already processed (dedup working): {e}")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        db.close()


def run_cancellation_test(label: str, email_path: str):
    """
    Cancellation test — booking_service will try to find the booking ID
    in the DB and update its status. Since we don't have a matching
    confirmation in the DB during testing, it's expected to either:
      a) succeed if booking_service handles missing bookings gracefully, or
      b) save to failed_emails with "unknown booking" reason.
    Either outcome is correct — what we're testing here is that the
    PARSER extracts the right booking ID without crashing.
    """
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")

    # Test the parser directly, without going through the DB
    from app.parsers.router import parse_email
    try:
        email_text = load_email(email_path)
        result = parse_email(email_text)

        print("✅ Cancellation parsed successfully!")
        print(f"   Booking ID  : {result.get('booking_id')}")
        print(f"   Platform    : {result.get('platform')}")
        print(f"   Status      : {result.get('status')}")
        print(f"   Guest       : {result.get('guest_name', '(not extracted)')}")
        print(f"   Property    : {result.get('property_name', '(not extracted)')}")
        print()
        print("   ℹ️  Note: DB update not tested here — cancellation matching")
        print("      requires a confirmed booking already in the DB.")

    except Exception as e:
        print(f"❌ Parser error: {e}")


if __name__ == "__main__":
    # --- Confirmation tests (full pipeline including DB) ---
    run_test("Airbnb confirmation", "sample_airbnb.txt")
    run_test("VRBO confirmation (sample 1)", "sample_vrbo.txt")
    run_test("VRBO confirmation (sample 2)", "sample_vrbo_two.txt")

    # --- Cancellation tests (parser only, no DB needed) ---
    run_cancellation_test("Airbnb cancellation", "sample_airbnb_cancel.txt")

    # --- Deduplication test (run the same email twice) ---
    print(f"\n{'='*50}")
    print("  Deduplication test (same email twice)")
    print(f"{'='*50}")
    fixed_id = "dedup-test-" + str(uuid.uuid4())
    db = SessionLocal()
    try:
        email_text = load_email("sample_airbnb.txt")
        process_email(db=db, email_text=email_text, message_id=fixed_id)
        print("First insert: ✅")
    except Exception as e:
        print(f"First insert failed: {e}")
    finally:
        db.close()

    db = SessionLocal()
    try:
        email_text = load_email("sample_airbnb.txt")
        process_email(db=db, email_text=email_text, message_id=fixed_id)
        print("❌ Second insert should have been blocked — dedup is broken!")
    except EmailAlreadyProcessed:
        print("Second insert blocked: ✅ (dedup working correctly)")
    except Exception as e:
        print(f"Second insert unexpected error: {e}")
    finally:
        db.close()