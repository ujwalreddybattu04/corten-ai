"""Shared test fixtures."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from src.main import app


@pytest_asyncio.fixture
async def client():
    """Async test client for the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
