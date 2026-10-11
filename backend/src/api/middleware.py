"""
API middleware — CORS, rate limiting, request logging.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.logging import logger
import time


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        logger.info(
            f"{request.method} {request.url.path} — {response.status_code} ({duration:.3f}s)"
        )
        return response
