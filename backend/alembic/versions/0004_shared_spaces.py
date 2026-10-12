"""Shared Spaces: roles, invitations, searchable files and shared threads.

Existing personal Spaces and the threads saved in them are copied from personal
storage, so every account keeps its Spaces as their owner.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None

ICONS = ("bookmark", "folder", "book", "briefcase", "code", "lightbulb", "graduation", "beaker", "pen", "trending")


def upgrade():
    op.add_column("spaces", sa.Column("icon", sa.String(30), nullable=False, server_default="bookmark"))
    op.add_column("spaces", sa.Column("color", sa.String(7), nullable=False, server_default="#6366f1"))
    op.add_column("spaces", sa.Column("links", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("spaces", sa.Column("web_search", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("spaces", sa.Column("legacy_id", sa.String(100), nullable=True))
    op.add_column("spaces", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint("uq_spaces_owner_legacy", "spaces", ["owner_id", "legacy_id"])

    op.create_table("space_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)))
    op.create_index("ix_space_invites_space", "space_invites", ["space_id"])
    op.create_index("ix_space_invites_email", "space_invites", ["email"])

    op.create_table("space_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("space_id", "sha256", name="uq_space_files_content"))
    op.create_index("ix_space_files_space", "space_files", ["space_id", "created_at"])

    op.create_table("space_file_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("space_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False))
    op.create_index("ix_space_file_chunks_file", "space_file_chunks", ["file_id", "ordinal"])
    op.create_index("ix_space_file_chunks_space", "space_file_chunks", ["space_id"])
    # 'simple' does not stem or drop words, so it behaves predictably for every language.
    op.execute("ALTER TABLE space_file_chunks ADD COLUMN search_vector tsvector "
               "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED")
    op.execute("CREATE INDEX ix_space_file_chunks_search ON space_file_chunks USING gin (search_vector)")

    op.create_table("space_threads",
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("thread_id", sa.String(100), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_space_threads_space_updated", "space_threads", ["space_id", "updated_at"])

    icons = ", ".join(f"'{icon}'" for icon in ICONS)
    op.execute(f"""
        INSERT INTO spaces (id, owner_id, name, description, custom_instructions, icon, color, links,
                            web_search, legacy_id, revision, created_at, updated_at)
        SELECT gen_random_uuid(), r.user_id, left(btrim(r.data->>'name'), 100),
               left(coalesce(r.data->>'description', ''), 2000), left(coalesce(r.data->>'instructions', ''), 8000),
               CASE WHEN r.data->>'icon' IN ({icons}) THEN r.data->>'icon' ELSE 'bookmark' END,
               CASE WHEN r.data->>'color' ~ '^#[0-9a-fA-F]{{6}}$' THEN r.data->>'color' ELSE '#6366f1' END,
               CASE WHEN jsonb_typeof(r.data->'links') = 'array' THEN r.data->'links' ELSE '[]'::jsonb END,
               true, r.record_id, 1,
               CASE WHEN r.data->>'createdAt' ~ '^[0-9]{{1,15}}$'
                    THEN to_timestamp((r.data->>'createdAt')::bigint / 1000.0) ELSE now() END,
               now()
        FROM personal_records r
        WHERE r.namespace = 'spaces' AND NOT r.deleted AND jsonb_typeof(r.data) = 'object'
          AND coalesce(btrim(r.data->>'name'), '') <> ''
        ON CONFLICT DO NOTHING
    """)
    op.execute("INSERT INTO space_members (space_id, user_id, role) SELECT id, owner_id, 'owner' FROM spaces "
               "ON CONFLICT DO NOTHING")
    op.execute("""
        INSERT INTO space_threads (space_id, thread_id, author_id, title, data, size_bytes)
        SELECT DISTINCT ON (s.id, t.record_id) s.id, t.record_id, s.owner_id,
               left(coalesce(nullif(btrim(t.data->>'title'), ''), nullif(btrim(t.data->>'query'), ''), 'Untitled thread'), 300),
               t.data, t.size_bytes
        FROM spaces s
        JOIN personal_records p ON p.user_id = s.owner_id AND p.namespace = 'spaces' AND p.record_id = s.legacy_id
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(p.data->'threadIds') = 'array' THEN p.data->'threadIds' ELSE '[]'::jsonb END
        ) AS tid(value)
        JOIN personal_records t ON t.user_id = s.owner_id AND t.namespace = 'threads'
             AND t.record_id = tid.value AND NOT t.deleted AND jsonb_typeof(t.data) = 'object'
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_table("space_threads")
    op.drop_table("space_file_chunks")
    op.drop_table("space_files")
    op.drop_table("space_invites")
    op.drop_constraint("uq_spaces_owner_legacy", "spaces", type_="unique")
    for column in ("revision", "legacy_id", "web_search", "links", "color", "icon"):
        op.drop_column("spaces", column)
