"""Initial schema — all tables, pgvector extension, and indexes.

Revision ID: 0001
Revises:
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("subscription_tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_provider_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_count_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_count_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_oauth", "users", ["oauth_provider", "oauth_provider_id"])
    op.create_index("ix_users_subscription_active", "users", ["subscription_tier", "is_active"])

    # ── spaces ───────────────────────────────────────────────────────────────
    op.create_table(
        "spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_spaces_owner", "spaces", ["owner_id"])

    # ── space_members ────────────────────────────────────────────────────────
    op.create_table(
        "space_members",
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_space_members_user", "space_members", ["user_id"])

    # ── threads ──────────────────────────────────────────────────────────────
    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("focus_mode", sa.String(50), nullable=False, server_default="all"),
        sa.Column("model_used", sa.String(100), nullable=False, server_default="llama-3.1-8b-instant"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("share_token", sa.String(64), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("share_token", name="uq_threads_share_token"),
    )
    op.create_index("ix_threads_user_updated", "threads", ["user_id", "updated_at"])
    op.create_index("ix_threads_user_space", "threads", ["user_id", "space_id"])
    op.create_index("ix_threads_share_token", "threads", ["share_token"])
    op.create_index("ix_threads_search_vector", "threads", ["search_vector"], postgresql_using="gin")

    # ── messages ─────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("search_provider", sa.String(50), nullable=True),
        sa.Column("search_query", sa.Text(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("query_embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_messages_thread_created", "messages", ["thread_id", "created_at"])
    # Convert to pgvector type and add HNSW index
    op.execute("ALTER TABLE messages ALTER COLUMN query_embedding TYPE vector(1536) USING NULL")
    op.execute(
        "CREATE INDEX ix_messages_query_embedding ON messages "
        "USING hnsw (query_embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── sources ──────────────────────────────────────────────────────────────
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("favicon_url", sa.String(500), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sources_message", "sources", ["message_id"])

    # ── collections ──────────────────────────────────────────────────────────
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_collections_user", "collections", ["user_id"])

    # ── collection_threads (many-to-many) ─────────────────────────────────────
    op.create_table(
        "collection_threads",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── group_threads ─────────────────────────────────────────────────────────
    op.create_table(
        "group_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("creator_name", sa.String(100), nullable=False),
        sa.Column("thread_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token", name="uq_group_threads_token"),
    )
    op.create_index("ix_group_threads_token", "group_threads", ["token"])
    op.create_index("ix_group_threads_created", "group_threads", ["created_at"])

    # ── group_members ─────────────────────────────────────────────────────────
    op.create_table(
        "group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("group_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_token", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("is_creator", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("member_token", name="uq_group_members_token"),
    )
    op.create_index("ix_group_members_group", "group_members", ["group_thread_id"])
    op.create_index("ix_group_members_token", "group_members", ["member_token"])

    # ── group_messages ────────────────────────────────────────────────────────
    op.create_table(
        "group_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("group_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("group_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_type", sa.String(20), nullable=False, server_default="message"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sender_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_group_messages_thread_created", "group_messages", ["group_thread_id", "created_at"])


def downgrade() -> None:
    op.drop_table("group_messages")
    op.drop_table("group_members")
    op.drop_table("group_threads")
    op.drop_table("collection_threads")
    op.drop_table("collections")
    op.drop_table("sources")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("space_members")
    op.drop_table("spaces")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS vector")
