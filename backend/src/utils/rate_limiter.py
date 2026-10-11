"""
Redis-backed rate limiter (replaces in-memory dict).

Uses Redis INCR + EXPIRE for atomic sliding window counters.
Works correctly across multiple worker processes and server instances.
Falls back to allowing requests if Redis is unavailable (fail-open).
"""

import logging
from src.db.redis import rate_limit_check

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def is_allowed(self, key: str) -> bool:
        """Check rate limit. Returns True if request is allowed."""
        count, allowed = await rate_limit_check(key, self.max_requests, self.window_seconds)
        if not allowed:
            logger.info("Rate limit exceeded for key=%s (count=%d, limit=%d)", key, count, self.max_requests)
        return allowed

    async def is_allowed_sync_compat(self, key: str) -> bool:
        """Async wrapper kept for backwards compatibility."""
        return await self.is_allowed(key)
