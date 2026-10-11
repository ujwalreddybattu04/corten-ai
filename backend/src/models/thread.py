"""
Thread ORM model — conversation container.
"""

import uuid
import secrets
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, TSVECTOR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base import Base


class Thread(Base):
    __tablename__ = "threads"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    space_id = Column(PG_UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(500), nullable=False)
    focus_mode = Column(String(50), nullable=False, default="all")
    model_used = Column(String(100), nullable=False, default="llama-3.1-8b-instant")
    is_public = Column(Boolean, nullable=False, default=False)          # share feature
    share_token = Column(String(64), unique=True, nullable=True)        # short public share URL token
    message_count = Column(Integer, nullable=False, default=0)          # denormalized: avoids COUNT(*) on inbox
    last_message_at = Column(DateTime(timezone=True), nullable=True)    # for inbox sort
    search_vector = Column(TSVECTOR, nullable=True)                     # full-text search on title
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_threads_user_updated", "user_id", "updated_at"),
        Index("ix_threads_user_space", "user_id", "space_id"),
        Index("ix_threads_share_token", "share_token"),
        Index("ix_threads_search_vector", "search_vector", postgresql_using="gin"),
    )

    @staticmethod
    def generate_share_token() -> str:
        return secrets.token_urlsafe(32)
