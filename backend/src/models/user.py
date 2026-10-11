"""
User ORM model.
"""

import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.sql import func
from src.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)          # Null for OAuth-only users
    avatar_url = Column(String(500), nullable=True)
    subscription_tier = Column(String(20), nullable=False, default="free")  # free | pro | team
    preferences = Column(JSONB, nullable=False, default=dict, server_default="{}")
    oauth_provider = Column(String(50), nullable=True)          # google | github | None
    oauth_provider_id = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_active_at = Column(DateTime(timezone=True), nullable=True)
    search_count_today = Column(Integer, nullable=False, default=0)
    search_count_month = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_oauth", "oauth_provider", "oauth_provider_id"),
        Index("ix_users_subscription_active", "subscription_tier", "is_active"),
    )
