from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import sys
import os

# Make sure 'src' is importable when running alembic from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so autogenerate can detect them ─────────────────────────
from src.db.base import Base  # noqa: F401
from src.models import user, thread, message, source, space, collection, personal_record  # noqa: F401

target_metadata = Base.metadata

# ── Load DATABASE_URL from settings (never hardcode in alembic.ini) ───────────
from src.config.settings import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,          # detect column type changes
        compare_server_default=True,  # detect server default changes
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects directly to DB)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,    # NullPool: one connection per migration run, no pooling
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}
        if "asyncpg" in settings.DATABASE_URL else {},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


import asyncio

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
