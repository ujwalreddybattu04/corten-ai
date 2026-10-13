"""Add immutable public Pharma snapshots, events, aliases and shared briefs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = depends_on = None

def upgrade():
    op.create_table("pharma_documents",sa.Column("id",sa.String(240),primary_key=True),
        sa.Column("source",sa.String(32),nullable=False),sa.Column("latest_version",sa.String(64),nullable=False),
        sa.Column("item",postgresql.JSONB(),nullable=False),sa.Column("event_date",sa.Date(),nullable=False),
        sa.Column("first_observed_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("observed_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_pharma_documents_source_date","pharma_documents",["source","event_date","id"])
    op.create_table("pharma_snapshots",sa.Column("document_id",sa.String(240),sa.ForeignKey("pharma_documents.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("version",sa.String(64),primary_key=True),sa.Column("raw",postgresql.JSONB(),nullable=False),
        sa.Column("item",postgresql.JSONB(),nullable=False),sa.Column("recorded_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_table("pharma_events",sa.Column("id",sa.String(64),primary_key=True),
        sa.Column("document_id",sa.String(240),sa.ForeignKey("pharma_documents.id",ondelete="CASCADE"),nullable=False),
        sa.Column("version",sa.String(64),nullable=False),sa.Column("event_date",sa.Date(),nullable=False),
        sa.Column("kind",sa.String(40),nullable=False),sa.Column("impact",sa.String(12),nullable=False),sa.Column("evidence",postgresql.JSONB(),nullable=False),
        sa.ForeignKeyConstraint(["document_id","version"],["pharma_snapshots.document_id","pharma_snapshots.version"],ondelete="CASCADE"))
    op.create_index("ix_pharma_events_document_date","pharma_events",["document_id","event_date"])
    op.create_index("ix_pharma_events_date_impact","pharma_events",["event_date","impact"])
    op.create_table("pharma_drugs",sa.Column("id",sa.String(64),primary_key=True),sa.Column("name",sa.String(240),nullable=False),
        sa.Column("ingredients",postgresql.JSONB(),nullable=False),sa.Column("evidence_url",sa.Text(),nullable=False))
    op.create_table("pharma_drug_aliases",sa.Column("alias",sa.String(240),primary_key=True),
        sa.Column("drug_id",sa.String(64),sa.ForeignKey("pharma_drugs.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("display_name",sa.String(240),nullable=False),sa.Column("evidence_url",sa.Text(),nullable=False))
    op.create_table("pharma_event_drugs",sa.Column("event_id",sa.String(64),sa.ForeignKey("pharma_events.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("drug_id",sa.String(64),sa.ForeignKey("pharma_drugs.id",ondelete="CASCADE"),primary_key=True))
    op.create_index("ix_pharma_event_drugs_drug","pharma_event_drugs",["drug_id","event_id"])
    op.create_table("pharma_source_states",sa.Column("id",sa.String(32),primary_key=True),sa.Column("status",sa.String(32),nullable=False),
        sa.Column("checked_at",sa.DateTime(timezone=True)),sa.Column("attempted_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("metadata_json",postgresql.JSONB(),nullable=False))
    op.create_table("pharma_shared_briefs",sa.Column("key",sa.String(64),primary_key=True),
        sa.Column("document_id",sa.String(240),sa.ForeignKey("pharma_documents.id",ondelete="CASCADE"),nullable=False),
        sa.Column("version",sa.String(64),nullable=False),sa.Column("contract",sa.String(80),nullable=False),
        sa.Column("model",sa.String(160),nullable=False),sa.Column("status",sa.String(12),nullable=False),
        sa.Column("owner",sa.String(32)),sa.Column("lease_until",sa.DateTime(timezone=True)),sa.Column("answer",sa.Text()),
        sa.Column("usage",postgresql.JSONB(),nullable=False,server_default="{}"),sa.Column("generated_at",sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["document_id","version"],["pharma_snapshots.document_id","pharma_snapshots.version"],ondelete="CASCADE"))
    op.create_index("ix_pharma_shared_briefs_document","pharma_shared_briefs",["document_id","version"])

def downgrade():
    for name in ("pharma_shared_briefs","pharma_source_states","pharma_event_drugs","pharma_drug_aliases","pharma_drugs","pharma_events","pharma_snapshots","pharma_documents"):
        op.drop_table(name)
