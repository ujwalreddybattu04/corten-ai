"""Bounded shared public-data cache and token-owned refresh leases.

No user data or provider credentials are stored. Redis failures fall back to the
service's process cache; this is degraded operation, not a multi-region guarantee.
"""
import asyncio
import json
import logging

from src.db.redis import get_redis

logger = logging.getLogger(__name__)
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"


class PharmaSharedCache:
    def __init__(self):
        self._offline_until = 0.0

    async def _run(self, operation, fallback=None):
        loop = asyncio.get_running_loop()
        if loop.time() < self._offline_until:
            return fallback
        try:
            async with asyncio.timeout(0.5):
                return await operation(await get_redis())
        except Exception:
            self._offline_until = loop.time() + 30
            logger.warning("Pharma shared cache unavailable; using bounded process cache")
            return fallback

    async def get(self, key):
        raw = await self._run(lambda r: r.get(key))
        if not isinstance(raw, str) or len(raw) > 1_000_000:
            return None
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except ValueError:
            return None

    async def set(self, key, value, ttl):
        raw=json.dumps(value)
        if len(raw)>1_000_000:return None
        return await self._run(lambda r: r.set(key, raw, ex=ttl))

    async def acquire(self, key, token):
        # None = Redis unavailable; False = another worker owns the lease.
        return await self._run(lambda r: r.set(key, token, nx=True, ex=20))

    async def release(self, key, token):
        await self._run(lambda r: r.eval(RELEASE, 1, key, token))
