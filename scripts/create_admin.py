from app.db.database import SessionLocal
from app.db.models import User
from app.utils.security import hash_password

db = SessionLocal()

email = "admin@client.com"
password = "AdminPassword123"

user = User(
    email=email,
    password_hash=hash_password(password)
)

db.add(user)
db.commit()

print("Admin user created")