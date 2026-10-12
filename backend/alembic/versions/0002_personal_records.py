"""Add owner-scoped personal cloud storage without changing existing data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("personal_revisions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_table("personal_records",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("namespace", sa.String(24), primary_key=True),
        sa.Column("record_id", sa.String(100), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_personal_records_changes", "personal_records", ["user_id", "revision"])


def downgrade():
    op.drop_table("personal_records")
    op.drop_table("personal_revisions")
