"""Security state is authoritative in Redis; outages must never permit access."""
import hashlib
import logging
from fastapi import HTTPException
from src.db.redis import get_redis

logger = logging.getLogger(__name__)


async def _eval(script, keys, *args):
    try:
        redis = await get_redis()
        return await redis.eval(script, len(keys), *keys, *args)
    except Exception:
        logger.warning("Authentication session store unavailable")
        raise HTTPException(503, "Authentication is temporarily unavailable. Please try again shortly.", headers={"Retry-After": "10"}) from None


def _key(sid):
    return f"auth_session:{sid}"


async def create_session(sid, user_id, jti, ttl):
    await _eval("redis.call('HSET', KEYS[1], 'user', ARGV[1], 'jti', ARGV[2]); redis.call('EXPIRE', KEYS[1], ARGV[3]); return 1", [_key(sid)], user_id, jti, ttl)


async def session_active(sid, user_id):
    return bool(await _eval("return redis.call('HGET', KEYS[1], 'user') == ARGV[1] and 1 or 0", [_key(sid)], user_id))


async def rotate_session(sid, user_id, old_jti, new_jti):
    # One atomic compare-and-swap. Rotation preserves the session's absolute expiry.
    return bool(await _eval("""
        if redis.call('HGET', KEYS[1], 'user') ~= ARGV[1] then return 0 end
        if redis.call('HGET', KEYS[1], 'jti') ~= ARGV[2] then redis.call('DEL', KEYS[1]); return 0 end
        redis.call('HSET', KEYS[1], 'jti', ARGV[3]); return 1
    """, [_key(sid)], user_id, old_jti, new_jti))


async def revoke_session(sid, user_id):
    await _eval("if redis.call('HGET', KEYS[1], 'user') == ARGV[1] then return redis.call('DEL', KEYS[1]) end; return 0", [_key(sid)], user_id)


async def limit_auth_attempts(action, email, client, email_limit=20, client_limit=1000):
    # Fixed windows, atomic expiry and bounded keys. Never store raw email addresses.
    for kind, value, limit in (("email", email.strip().lower(), email_limit), ("client", client, client_limit)):
        digest = hashlib.sha256(value.encode()).hexdigest()
        count = await _eval("local n = redis.call('INCR', KEYS[1]); if n == 1 then redis.call('EXPIRE', KEYS[1], 900) end; return n", [f"auth_limit:{action}:{kind}:{digest}"])
        if count > limit:
            raise HTTPException(429, "Too many attempts. Please try again later.", headers={"Retry-After": "900"})
