"""Shared Redis budgets for public generation. Outages fail closed, never bypass limits."""
import hashlib
import ipaddress
import time
from starlette.responses import JSONResponse
from src.config.settings import settings
from src.core.security import decode_token
from src.db.redis import get_redis

PATHS = {"/api/v1/search/stream", "/api/v1/search/title", "/api/v1/report/stream", "/api/v1/discover/article/summarize", "/api/v1/pharma/analysis/stream", "/api/v1/pharma/research/stream", "/api/v1/pharma/deep/plan"}
LUA = """
local minute = tonumber(redis.call('GET', KEYS[1]) or '0')
local day = tonumber(redis.call('GET', KEYS[2]) or '0')
if minute >= tonumber(ARGV[1]) then return {0, tonumber(ARGV[3])} end
if day >= tonumber(ARGV[2]) then return {0, tonumber(ARGV[4])} end
redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], ARGV[4])
return {1, 0}
"""


async def check_budget(identity, now=None):
    now = int(time.time() if now is None else now)
    digest = hashlib.sha256(identity.encode()).hexdigest()
    minute_ttl, day_ttl = 60-now%60, 86400-now%86400
    redis = await get_redis()
    # The hash tag also keeps both counters together if Redis is clustered later.
    prefix = "generation:{"+digest+"}:"
    return await redis.eval(LUA, 2, prefix+"minute:"+str(now//60), prefix+"day:"+str(now//86400),
        settings.RATE_LIMIT_PER_MINUTE, settings.RATE_LIMIT_PER_DAY, minute_ttl, day_ttl)


class GenerationLimits:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        deep_start=scope.get('path','').startswith('/api/v1/pharma/deep/') and scope.get('path','').endswith(('/start','/retry'))
        if settings.APP_ENV != "production" or scope["type"] != "http" or scope.get("method") != "POST" or (scope.get("path") not in PATHS and not deep_start):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        payload = decode_token(authorization[7:]) if authorization.startswith("Bearer ") else None
        if payload:
            identity = "account:"+payload["sub"]
        else:
            # The private backend only accepts service traffic. The frontend generates
            # this header from Nginx's trusted CloudFront viewer IP, never from a caller override.
            raw = headers.get(b"x-corten-client-ip", b"").decode("ascii", errors="ignore")
            try: client = str(ipaddress.ip_address(raw))
            except ValueError: client = scope.get("client", ("unknown",))[0]
            identity = "guest:"+client
        try:
            allowed, delay = await check_budget(identity)
        except Exception:
            return await JSONResponse({"detail":"Generation is temporarily unavailable. Please retry shortly."}, status_code=503,
                headers={"Retry-After":"10", "Cache-Control":"no-store"})(scope, receive, send)
        if not allowed:
            return await JSONResponse({"detail":"Your AI request limit has been reached. Please retry after the current limit resets."}, status_code=429,
                headers={"Retry-After":str(delay), "Cache-Control":"no-store"})(scope, receive, send)
        await self.app(scope, receive, send)
