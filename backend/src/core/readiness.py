"""Dependency readiness is separate from the process liveness endpoint."""
import asyncio
from sqlalchemy import text
from src.db.session import engine
from src.db.redis import get_redis


async def database_ready():
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def cache_ready():
    redis = await get_redis()
    await redis.ping()


async def readiness():
    async def check(operation):
        try:
            await asyncio.wait_for(operation(), timeout=3)
            return True
        except Exception:
            return False
    database, cache = await asyncio.gather(check(database_ready), check(cache_ready))
    checks = {"database": database, "cache": cache}
    return {"status": "ready" if all(checks.values()) else "not_ready", "checks": checks}
