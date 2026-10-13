"""
Shared Spaces: membership roles, invitations, knowledge files and shared threads.
"""

import uuid
from sqlalchemy import (Column, String, Text, DateTime, ForeignKey, Index, Integer, BigInteger, Boolean,
    JSON, UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base import Base

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Space(Base):
    __tablename__ = "spaces"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    custom_instructions = Column(Text, nullable=True)
    icon = Column(String(30), nullable=False, default="bookmark", server_default="bookmark")
    color = Column(String(7), nullable=False, default="#6366f1", server_default="#6366f1")
    links = Column(JSON_DOCUMENT, nullable=False, default=list)
    web_search = Column(Boolean, nullable=False, default=True, server_default="true")
    # The template the Space was created from (its agent's tools and sources); empty for custom Spaces.
    template = Column(String(40), nullable=True)
    # Browser/personal-storage identity of a Space imported from the earlier single-user design.
    legacy_id = Column(String(100), nullable=True)
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    members = relationship("SpaceMember", back_populates="space", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_spaces_owner", "owner_id"),
        UniqueConstraint("owner_id", "legacy_id", name="uq_spaces_owner_legacy"),
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


class SpaceInvite(Base):
    """A link invitation, or an invitation addressed to one email. Only token hashes are stored."""
    __tablename__ = "space_invites"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(PG_UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    email = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False)
    created_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_space_invites_space", "space_id"),
        Index("ix_space_invites_email", "email"),
    )


class SpaceFile(Base):
    __tablename__ = "space_files"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(PG_UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    char_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_space_files_space", "space_id", "created_at"),
        UniqueConstraint("space_id", "sha256", name="uq_space_files_content"),
    )


class SpaceFileChunk(Base):
    """Searchable extracted text. PostgreSQL adds a generated full-text vector column."""
    __tablename__ = "space_file_chunks"

    id = Column(BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    file_id = Column(PG_UUID(as_uuid=True), ForeignKey("space_files.id", ondelete="CASCADE"), nullable=False)
    space_id = Column(PG_UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_space_file_chunks_file", "file_id", "ordinal"),
        Index("ix_space_file_chunks_space", "space_id"),
    )


class SpaceThread(Base):
    """A member's conversation saved to a Space, readable by every member."""
    __tablename__ = "space_threads"

    space_id = Column(PG_UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), primary_key=True)
    thread_id = Column(String(100), primary_key=True)
    author_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(300), nullable=False)
    data = Column(JSON_DOCUMENT, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_space_threads_space_updated", "space_id", "updated_at"),
    )
