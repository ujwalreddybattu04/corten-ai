"""Shared test fixtures."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from src.config.settings import settings
from src.main import app


@pytest_asyncio.fixture
async def client():
    """Async test client for the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def classic_space_answers(monkeypatch):
    """Space agents call a live model and live data sources. Tests of the answer pipeline patch the standard path,
    so agents are off unless a test turns them on with fakes (see test_space_agents.py)."""
    monkeypatch.setattr(settings, "SPACE_AGENTS_ENABLED", False)
