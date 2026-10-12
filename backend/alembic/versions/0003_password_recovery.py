"""Add expiring password recovery and revoke sessions through a user version."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None

def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("password_resets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])
    op.create_table("recovery_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("password_resets.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("payload", sa.String(40000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt", sa.String(200)),
        sa.Column("lease", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_recovery_emails_status", "recovery_emails", ["status"])

def downgrade():
    op.drop_table("recovery_emails")
    op.drop_table("password_resets")
    op.drop_column("users", "auth_version")
