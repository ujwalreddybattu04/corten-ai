"""
Message ORM model — individual messages within a thread.
"""

import uuid
from sqlalchemy import Column, String, Text, DateTime, Integer, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base import Base

try:
    from pgvector.sqlalchemy import Vector
    _PGVECTOR_AVAILABLE = True
except ImportError:
    Vector = None
    _PGVECTOR_AVAILABLE = False


class Message(Base):
    __tablename__ = "messages"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(PG_UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)                       # user | assistant | system
    content = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    search_provider = Column(String(50), nullable=True)             # tavily | brave | serper
    search_query = Column(Text, nullable=True)                      # actual query sent to search API
    processing_time_ms = Column(Integer, nullable=True)             # observability
    # Vector embedding for semantic "related questions" feature (pgvector)
    query_embedding = Column(Vector(1536), nullable=True) if _PGVECTOR_AVAILABLE and Vector else Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    thread = relationship("Thread", back_populates="messages")
    sources = relationship("Source", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_messages_thread_created", "thread_id", "created_at"),
    )
