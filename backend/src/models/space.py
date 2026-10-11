"""
Space ORM model — collaborative workspace with membership.
"""

import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base import Base


class Space(Base):
    __tablename__ = "spaces"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    custom_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    members = relationship("SpaceMember", back_populates="space", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_spaces_owner", "owner_id"),
    )


class SpaceMember(Base):
    """Membership table: spaces <-> users with role."""
    __tablename__ = "space_members"

    space_id = Column(PG_UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(20), nullable=False, default="viewer")     # owner | editor | viewer
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    space = relationship("Space", back_populates="members")

    __table_args__ = (
        Index("ix_space_members_user", "user_id"),
    )
