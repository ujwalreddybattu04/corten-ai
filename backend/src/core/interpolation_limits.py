"""Limit upload request bodies before the multipart parser spools them."""
import re
from fastapi import HTTPException
from starlette.responses import JSONResponse
from src.config.settings import settings
from src.services.interpolation import MAX_UPLOAD_BYTES

SPACE_UPLOAD = re.compile(r"^/api/v1/spaces/[^/]+/files$")


def upload_limit(path: str):
    """Return (byte limit, message) for bounded upload paths, or None."""
    if path.startswith("/api/v1/interpolation/"):
        return MAX_UPLOAD_BYTES, "CSV files must be no larger than 10 MB."
    if SPACE_UPLOAD.match(path):
        return settings.SPACE_MAX_FILE_BYTES, f"Files must be no larger than {settings.SPACE_MAX_FILE_BYTES // (1024 * 1024)} MB."
    if path == "/api/v1/attachments":
        return settings.ATTACHMENT_MAX_BYTES, f"Files must be no larger than {settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB."
    return None


class InterpolationBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        bounded = upload_limit(scope.get("path", "")) if scope["type"] == "http" else None
        if not bounded:
            return await self.app(scope, receive, send)
        # Allow multipart headers in addition to the bounded file itself.
        limit, message = bounded[0] + 64 * 1024, bounded[1]
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid request length."}, status_code=400, headers={"Cache-Control": "no-store"})(scope, receive, send)
        if declared > limit:
            return await JSONResponse({"detail": message}, status_code=413,
                                      headers={"Cache-Control": "no-store"})(scope, receive, send)
        size = 0

        async def bounded_receive():
            nonlocal size
            message_part = await receive()
            size += len(message_part.get("body", b""))
            if size > limit:
                raise HTTPException(413, message)
            return message_part

        async def no_store_send(message_part):
            if message_part["type"] == "http.response.start":
                message_part = {**message_part, "headers": [(key, value) for key, value in message_part.get("headers", []) if key.lower() != b"cache-control"] + [(b"cache-control", b"no-store")]}
            await send(message_part)

        await self.app(scope, bounded_receive, no_store_send)
