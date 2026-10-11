"""
Redis client — async connection with caching helpers.

Use cases:
  1. Rate limiting (sliding window counter)
  2. JWT refresh token store / revocation
  3. User session cache (avoid DB hit on every request)
  4. Search result cache (Tavily/Serper API response cache)
  5. Group thread pub/sub (real-time messaging)
"""

import json
import hashlib
import logging
from typing import Any, Optional
from redis.asyncio import Redis, ConnectionPool
from src.config.settings import settings

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None
_redis: Optional[Redis] = None


async def get_redis() -> Redis:
    """Get or create the Redis connection (singleton)."""
    global _redis, _pool
    if _redis is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=50,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        _redis = Redis(connection_pool=_pool)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection on shutdown."""
    global _redis, _pool
    if _redis:
        await _redis.aclose()
        _redis = None
    if _pool:
        await _pool.aclose()
        _pool = None


# ─── Cache helpers ────────────────────────────────────────────────────────────

def make_cache_key(prefix: str, *parts: str) -> str:
    """Build a namespaced cache key."""
    return f"{prefix}:" + ":".join(str(p) for p in parts)


def make_search_cache_key(query: str, focus_mode: str) -> str:
    """SHA-256 hash of normalized query + focus_mode for search result caching."""
    normalized = f"{query.strip().lower()}|{focus_mode}"
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"search_cache:{digest}"


async def cache_get(key: str) -> Optional[Any]:
    """Get a JSON-serialized value from Redis."""
    try:
        redis = await get_redis()
        value = await redis.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.warning("Redis cache_get failed for key=%s: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """Set a JSON-serialized value in Redis with TTL (seconds)."""
    try:
        redis = await get_redis()
        await redis.set(key, json.dumps(value), ex=ttl)
        return True
    except Exception as e:
        logger.warning("Redis cache_set failed for key=%s: %s", key, e)
        return False


async def cache_delete(key: str) -> None:
    """Delete a key from Redis."""
    try:
        redis = await get_redis()
        await redis.delete(key)
    except Exception as e:
        logger.warning("Redis cache_delete failed for key=%s: %s", key, e)


# ─── Rate limiting (sliding window) ───────────────────────────────────────────

async def rate_limit_check(identifier: str, limit: int, window_seconds: int) -> tuple[int, bool]:
    """
    Increment a rate limit counter. Returns (current_count, is_allowed).
    Uses Redis INCR + EXPIRE for atomic sliding window.
    """
    try:
        redis = await get_redis()
        key = f"rate_limit:{identifier}:{window_seconds}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        return count, count <= limit
    except Exception as e:
        logger.warning("Redis rate_limit_check failed for id=%s: %s", identifier, e)
        return 0, True  # Fail open — allow request if Redis is down


# ─── JWT refresh token store ───────────────────────────────────────────────────

async def store_refresh_token(jti: str, user_id: str, ttl: int) -> None:
    """Store a refresh token JTI for revocation checking."""
    try:
        redis = await get_redis()
        key = f"refresh_token:{jti}"
        await redis.set(key, str(user_id), ex=ttl)
    except Exception as e:
        logger.warning("Redis store_refresh_token failed: %s", e)


async def validate_refresh_token(jti: str) -> Optional[str]:
    """Return user_id if the refresh token is valid, None if revoked/expired."""
    try:
        redis = await get_redis()
        return await redis.get(f"refresh_token:{jti}")
    except Exception as e:
        logger.warning("Redis validate_refresh_token failed: %s", e)
        return None


async def revoke_refresh_token(jti: str) -> None:
    """Revoke a refresh token immediately."""
    await cache_delete(f"refresh_token:{jti}")
