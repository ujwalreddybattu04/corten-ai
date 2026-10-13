"""Public source archives and shared briefs. Personal conversations stay separate."""
from sqlalchemy import Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from src.db.base import Base


class PharmaDocument(Base):
    __tablename__ = "pharma_documents"
    id = Column(String(240), primary_key=True)
    source = Column(String(32), nullable=False)
    latest_version = Column(String(64), nullable=False)
    item = Column(JSONB, nullable=False)
    event_date = Column(Date, nullable=False)
    first_observed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    observed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (Index("ix_pharma_documents_source_date", "source", "event_date", "id"),)


class PharmaSnapshot(Base):
    __tablename__ = "pharma_snapshots"
    document_id = Column(String(240), ForeignKey("pharma_documents.id", ondelete="CASCADE"), primary_key=True)
    version = Column(String(64), primary_key=True)
    raw = Column(JSONB, nullable=False)
    item = Column(JSONB, nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PharmaEvent(Base):
    __tablename__ = "pharma_events"
    id = Column(String(64), primary_key=True)
    document_id = Column(String(240), ForeignKey("pharma_documents.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(64), nullable=False)
    event_date = Column(Date, nullable=False)
    kind = Column(String(40), nullable=False)
    impact = Column(String(12), nullable=False)
    evidence = Column(JSONB, nullable=False)
    __table_args__ = (Index("ix_pharma_events_document_date", "document_id", "event_date"),
                     Index("ix_pharma_events_date_impact", "event_date", "impact"),
                     ForeignKeyConstraint(["document_id","version"],["pharma_snapshots.document_id","pharma_snapshots.version"],ondelete="CASCADE"))


class PharmaDrug(Base):
    __tablename__ = "pharma_drugs"
    id = Column(String(64), primary_key=True)
    name = Column(String(240), nullable=False)
    ingredients = Column(JSONB, nullable=False)
    evidence_url = Column(Text, nullable=False)


class PharmaDrugAlias(Base):
    __tablename__ = "pharma_drug_aliases"
    alias = Column(String(240), primary_key=True)
    drug_id = Column(String(64), ForeignKey("pharma_drugs.id", ondelete="CASCADE"), primary_key=True)
    display_name = Column(String(240), nullable=False)
    evidence_url = Column(Text, nullable=False)


class PharmaEventDrug(Base):
    __tablename__ = "pharma_event_drugs"
    event_id = Column(String(64), ForeignKey("pharma_events.id", ondelete="CASCADE"), primary_key=True)
    drug_id = Column(String(64), ForeignKey("pharma_drugs.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (Index("ix_pharma_event_drugs_drug", "drug_id", "event_id"),)


class PharmaSourceState(Base):
    __tablename__ = "pharma_source_states"
    id = Column(String(32), primary_key=True)
    status = Column(String(32), nullable=False)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    attempted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    metadata_json = Column(JSONB, nullable=False)


class PharmaSharedBrief(Base):
    __tablename__ = "pharma_shared_briefs"
    key = Column(String(64), primary_key=True)
    document_id = Column(String(240), ForeignKey("pharma_documents.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(64), nullable=False)
    contract = Column(String(80), nullable=False)
    model = Column(String(160), nullable=False)
    status = Column(String(12), nullable=False)
    owner = Column(String(32), nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    answer = Column(Text, nullable=True)
    usage = Column(JSONB, nullable=False, default=dict, server_default="{}")
    generated_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_pharma_shared_briefs_document", "document_id", "version"),
                     ForeignKeyConstraint(["document_id","version"],["pharma_snapshots.document_id","pharma_snapshots.version"],ondelete="CASCADE"))
