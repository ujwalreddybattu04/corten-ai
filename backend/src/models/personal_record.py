"""Owner-scoped personal records, incremental revisions and deletion tombstones."""
from sqlalchemy import Column, String, BigInteger, Integer, Boolean, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.db.base import Base


class PersonalRevision(Base):
    __tablename__ = "personal_revisions"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    revision = Column(BigInteger, nullable=False, default=0)


class PersonalRecord(Base):
    __tablename__ = "personal_records"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    namespace = Column(String(24), primary_key=True)
    record_id = Column(String(100), primary_key=True)
    data = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    deleted = Column(Boolean, nullable=False, default=False)
    revision = Column(BigInteger, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    __table_args__ = (Index("ix_personal_records_changes", "user_id", "revision"),)
