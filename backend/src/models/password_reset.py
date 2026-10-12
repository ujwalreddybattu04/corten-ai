"""Expiring one-use recovery tokens and an encrypted transactional email outbox."""
import uuid
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from src.db.base import Base

class PasswordReset(Base):
    __tablename__ = "password_resets"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    digest = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class RecoveryEmail(Base):
    __tablename__ = "recovery_emails"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reset_id = Column(PG_UUID(as_uuid=True), ForeignKey("password_resets.id", ondelete="CASCADE"), nullable=False, unique=True)
    payload = Column(String(40000), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    receipt = Column(String(200), nullable=True)
    lease = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
