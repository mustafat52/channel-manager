"""
scripts/seed_properties.py

Seeds the 7 known Vrbo properties into the properties table.
Run once after the migration:

    python -m scripts.seed_properties

Safe to re-run — uses INSERT ... ON CONFLICT DO UPDATE so existing rows
are updated in place (name corrected if it was wrong) rather than duplicated.
"""

import sys
import os

# ── Make sure app/ is importable when running from project root ───────────────
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal
from app.db.models import Property

# ── Vrbo property codes → real names (from client) ────────────────────────────
VRBO_PROPERTIES = [
    {"vrbo_code": "2500513", "name": "Silversmith"},
    {"vrbo_code": "4989700", "name": "Peerless Unit C"},
    {"vrbo_code": "3274355", "name": "Rosenberg"},
    {"vrbo_code": "4034088", "name": "Stassen"},
    {"vrbo_code": "2630601", "name": "Elkana"},
    {"vrbo_code": "4993257", "name": "Peerless Unit A"},
    {"vrbo_code": "1198288", "name": "Blodgett"},
]


def seed():
    db = SessionLocal()
    inserted = 0
    updated = 0

    try:
        for entry in VRBO_PROPERTIES:
            existing = (
                db.query(Property)
                .filter(Property.vrbo_code == entry["vrbo_code"])
                .first()
            )

            if existing:
                if existing.name != entry["name"]:
                    print(f"  Updating  [{entry['vrbo_code']}] '{existing.name}' → '{entry['name']}'")
                    existing.name = entry["name"]
                    updated += 1
                else:
                    print(f"  Skipping  [{entry['vrbo_code']}] '{entry['name']}' — already up to date")
            else:
                prop = Property(
                    name=entry["name"],
                    vrbo_code=entry["vrbo_code"],
                    is_active=True,
                )
                db.add(prop)
                print(f"  Inserting [{entry['vrbo_code']}] '{entry['name']}'")
                inserted += 1

        db.commit()
        print(f"\nDone — {inserted} inserted, {updated} updated, "
              f"{len(VRBO_PROPERTIES) - inserted - updated} already current.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding Vrbo properties...\n")
    seed()