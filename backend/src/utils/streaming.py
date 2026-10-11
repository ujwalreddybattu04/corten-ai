"""SSE streaming response helpers."""
import json
from typing import AsyncGenerator


async def create_sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


async def token_event(content: str) -> str:
    return await create_sse_event("token", {"content": content})


async def sources_event(sources: list) -> str:
    return await create_sse_event("sources", {"items": sources})


async def done_event() -> str:
    return await create_sse_event("done", {})


async def error_event(message: str) -> str:
    return await create_sse_event("error", {"message": message})
