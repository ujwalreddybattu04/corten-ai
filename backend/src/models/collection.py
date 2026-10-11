"""
Collection ORM model — user-organized groups of threads (bookmarks/libraries).
"""

import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Table, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base import Base


# Many-to-many join table: collections <-> threads
collection_threads = Table(
    "collection_threads",
    Base.metadata,
    Column("collection_id", PG_UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    Column("thread_id", PG_UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True),
)


class Collection(Base):
    __tablename__ = "collections"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    threads = relationship("Thread", secondary=collection_threads)

    __table_args__ = (
        Index("ix_collections_user", "user_id"),
    )
