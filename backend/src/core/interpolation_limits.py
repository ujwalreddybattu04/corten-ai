"""Limit interpolation request bodies before the multipart parser spools them."""
from fastapi import HTTPException
from starlette.responses import JSONResponse
from src.services.interpolation import MAX_UPLOAD_BYTES


class InterpolationBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/interpolation/"):
            return await self.app(scope, receive, send)
        # Allow multipart headers in addition to the bounded file itself.
        limit = MAX_UPLOAD_BYTES + 64 * 1024
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid request length."}, status_code=400, headers={"Cache-Control": "no-store"})(scope, receive, send)
        if declared > limit:
            return await JSONResponse({"detail": "CSV files must be no larger than 10 MB."}, status_code=413,
                                      headers={"Cache-Control": "no-store"})(scope, receive, send)
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                raise HTTPException(413, "CSV files must be no larger than 10 MB.")
            return message

        async def no_store_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [(key, value) for key, value in message.get("headers", []) if key.lower() != b"cache-control"] + [(b"cache-control", b"no-store")]}
            await send(message)

        await self.app(scope, bounded_receive, no_store_send)
