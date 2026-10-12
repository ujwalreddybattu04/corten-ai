"""Single release migration job with a cross-process PostgreSQL advisory lock."""
import asyncio
import sys
from sqlalchemy import text
from src.db.session import engine
from src.db.wait_ready import wait_for_database


async def migrate():
    await wait_for_database()
    try:
        async with engine.connect() as connection:
            deadline = asyncio.get_running_loop().time() + 120
            while not await connection.scalar(text("SELECT pg_try_advisory_lock(405893200)")):
                if asyncio.get_running_loop().time() >= deadline:
                    raise RuntimeError("Another release is still migrating the database")
                await asyncio.sleep(2)
            try:
                process = await asyncio.create_subprocess_exec(sys.executable, "-m", "alembic", "upgrade", "head")
                try:
                    code = await asyncio.wait_for(process.wait(), timeout=300)
                except asyncio.TimeoutError:
                    process.kill(); await process.wait()
                    raise RuntimeError("Database migration exceeded its release deadline") from None
                if code:
                    raise RuntimeError("Database migration failed; release must not receive traffic")
            finally:
                await connection.execute(text("SELECT pg_advisory_unlock(405893200)"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
