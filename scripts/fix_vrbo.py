"""
scripts/fix_vrbo_bookings.py

One-time script to re-link existing Vrbo bookings that were stored with
garbage property names like 'vrbo_property_4034088' to the real seeded
Property rows.

Run AFTER seed_properties.py:

    python -m scripts.fix_vrbo_bookings

Safe to re-run — skips bookings already pointing to the correct property.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.models import Booking, Property

def fix():
    db = SessionLocal()
    fixed = 0
    skipped = 0
    unknown = []

    try:
        # Find all Vrbo bookings
        vrbo_bookings = db.query(Booking).filter(Booking.platform == "vrbo").all()
        print(f"Found {len(vrbo_bookings)} Vrbo bookings\n")

        for booking in vrbo_bookings:
            current_property = db.query(Property).filter(
                Property.id == booking.property_id
            ).first()

            if not current_property:
                print(f"  [{booking.booking_id}] No property linked — skipping")
                skipped += 1
                continue

            # Already pointing to a real property (has no vrbo_property_ prefix)
            if not current_property.name.startswith("vrbo_property_"):
                print(f"  [{booking.booking_id}] Already correct: '{current_property.name}' — skipping")
                skipped += 1
                continue

            # Extract the numeric code from the garbage name
            vrbo_code = current_property.name.replace("vrbo_property_", "")

            # Look up the real property by code
            real_property = db.query(Property).filter(
                Property.vrbo_code == vrbo_code
            ).first()

            if not real_property:
                print(f"  [{booking.booking_id}] Unknown code '{vrbo_code}' — not in properties table")
                unknown.append((booking.booking_id, vrbo_code))
                continue

            # Re-link
            print(f"  [{booking.booking_id}] '{current_property.name}' → '{real_property.name}'")
            booking.property_id = real_property.id
            fixed += 1

        db.commit()

        print(f"\nDone — {fixed} fixed, {skipped} skipped.")

        if unknown:
            print(f"\n{len(unknown)} bookings have unrecognised Vrbo codes (not in seed):")
            for booking_id, code in unknown:
                print(f"  {booking_id} → code '{code}'")
            print("Add these codes to seed_properties.py and re-run both scripts.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Re-linking Vrbo bookings to real properties...\n")
    fix()