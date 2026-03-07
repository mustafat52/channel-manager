import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Date,
    DateTime,
    Integer,
    ForeignKey,
    Text,
    UniqueConstraint,
    Enum,
    JSON,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from datetime import datetime
from app.db.database import Base
from sqlalchemy import Column, Integer, String, Text, DateTime

# ---------------------------
# ENUMS
# ---------------------------

class BookingStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    modified = "modified"


# ---------------------------
# PROPERTIES
# ---------------------------

class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    bookings = relationship("Booking", back_populates="property")


# ---------------------------
# BOOKINGS
# ---------------------------

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    booking_id = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)

    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    property = relationship("Property", back_populates="bookings")

    guest_name = Column(String(255), nullable=True)
    booking_date = Column(DateTime(timezone=True), nullable=True)

    checkin_date = Column(Date, nullable=False)
    checkout_date = Column(Date, nullable=False)

    status = Column(Enum(BookingStatus), nullable=False)

    last_email_message_id = Column(String(255), nullable=True)

    notified_instant = Column(Boolean, default=False)
    notified_24hr = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("booking_id", "platform", name="unique_booking_platform"),
    )


# ---------------------------
# PROCESSED EMAILS
# ---------------------------

class ProcessedEmail(Base):
    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), unique=True, nullable=False)
    platform = Column(String(50), nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------
# NOTIFICATION LOGS
# ---------------------------

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)

    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)

    notification_type = Column(String(50), nullable=False)
    delivery_status = Column(String(50), nullable=True)

    response_payload = Column(JSON, nullable=True)

    sent_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------
# USERS
# ---------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), default="admin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())




class FailedEmail(Base):
    __tablename__ = "failed_emails"

    id = Column(Integer, primary_key=True, index=True)

    message_id = Column(String, index=True)

    error_message = Column(String)

    email_body = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)    