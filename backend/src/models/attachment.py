"""Files attached to chat messages, and files Corten generates for the user."""
import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Integer, BigInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from src.db.base import Base


class ChatAttachment(Base):
    __tablename__ = "chat_attachments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    kind = Column(String(12), nullable=False)          # image | document | generated
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    # Extracted text for documents; generated and image files have none.
    text = Column(Text, nullable=True)
    char_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_chat_attachments_user", "user_id", "created_at"),
        Index("ix_chat_attachments_expiry", "expires_at"),
    )


class UserMemory(Base):
    """A durable fact or preference Corten remembers for one user. Users can view, edit and delete it."""
    __tablename__ = "user_memories"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(String(500), nullable=False)
    source = Column(String(10), nullable=False, default="manual")   # manual | auto
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (Index("ix_user_memories_user", "user_id", "updated_at"),)
