"""
Source ORM model — cited sources for each message.
"""

import uuid
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base import Base


class Source(Base):
    __tablename__ = "sources"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(PG_UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    url = Column(String(2000), nullable=False)
    title = Column(String(500), nullable=False)
    domain = Column(String(255), nullable=False)
    favicon_url = Column(String(500), nullable=True)
    snippet = Column(Text, nullable=True)
    citation_index = Column(Integer, nullable=False)
    relevance_score = Column(Float, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("Message", back_populates="sources")

    __table_args__ = (
        Index("ix_sources_message", "message_id"),
    )
