import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import random
from datetime import date, timedelta
from app.db.database import SessionLocal
from app.db.models import Property, Booking, BookingStatus

db = SessionLocal()

# ---- Create Properties ----
property_names = [
    "Sunset Villa",
    "Ocean View Apartment",
    "Palm Stay",
    "Lake House"
]

properties = []

for name in property_names:
    prop = Property(name=name)
    db.add(prop)
    properties.append(prop)

db.commit()

# refresh ids
for p in properties:
    db.refresh(p)

# ---- Platforms ----
platforms = ["airbnb", "vrbo", "booking"]

# ---- Status types ----
statuses = [
    BookingStatus.confirmed,
    BookingStatus.cancelled,
    BookingStatus.modified
]

guest_names = [
    "John Smith",
    "Emma Wilson",
    "Ali Khan",
    "Maria Garcia",
    "David Lee",
    "Sophia Brown",
    "Lucas Martin",
    "Ava Thompson",
]

today = date.today()

# ---- Create Bookings ----
for i in range(60):

    checkin_offset = random.randint(-5, 30)
    stay_length = random.randint(1, 4)

    checkin = today + timedelta(days=checkin_offset)
    checkout = checkin + timedelta(days=stay_length)

    booking = Booking(
        booking_id=f"BKG-{1000+i}",
        platform=random.choice(platforms),
        property_id=random.choice(properties).id,
        guest_name=random.choice(guest_names),
        booking_date=today - timedelta(days=random.randint(1, 10)),
        checkin_date=checkin,
        checkout_date=checkout,
        status=random.choice(statuses)
    )

    db.add(booking)

db.commit()
db.close()

print("Fake bookings inserted successfully.")