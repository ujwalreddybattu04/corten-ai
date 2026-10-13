"""Limits protect expensive routes across workers without breaking read-only tools."""
from unittest.mock import AsyncMock
import pytest
import httpx
from src.core import generation_limits


async def response(scope, receive, send):
    await send({"type":"http.response.start", "status":200, "headers":[]})
    await send({"type":"http.response.body", "body":b"ok"})


@pytest.mark.asyncio
async def test_generation_budget_rejects_before_work_and_reports_retry(monkeypatch):
    monkeypatch.setattr(generation_limits.settings, "APP_ENV", "production")
    check = AsyncMock(return_value=[0, 42]); monkeypatch.setattr(generation_limits, "check_budget", check)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=generation_limits.GenerationLimits(response)), base_url="https://test") as client:
        result = await client.post("/api/v1/search/stream", headers={"X-Corten-Client-IP":"203.0.113.17"})
        assert result.status_code == 429 and result.headers["Retry-After"] == "42"
        assert (await client.get("/api/v1/search/status")).status_code == 200
        assert (await client.post("/api/v1/interpolation/preview")).status_code == 200
    check.assert_awaited_once_with("guest:203.0.113.17")


@pytest.mark.asyncio
async def test_budget_store_outage_does_not_allow_generation(monkeypatch):
    monkeypatch.setattr(generation_limits.settings, "APP_ENV", "production")
    monkeypatch.setattr(generation_limits, "check_budget", AsyncMock(side_effect=RuntimeError("private cache URL")))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=generation_limits.GenerationLimits(response)), base_url="https://test") as client:
        result = await client.post("/api/v1/report/stream")
        assert result.status_code == 503 and "private" not in result.text


@pytest.mark.asyncio
async def test_budget_uses_shared_atomic_counters_without_storing_identity(monkeypatch):
    redis = AsyncMock(); redis.eval.return_value = [1,0]
    monkeypatch.setattr(generation_limits, "get_redis", AsyncMock(return_value=redis))
    assert await generation_limits.check_budget("account:private-user", 90061) == [1,0]
    args = redis.eval.call_args.args
    assert "private-user" not in str(args)
    assert args[1] == 2 and args[-2:] == (59, 82739)


@pytest.mark.asyncio
async def test_pharma_answers_share_the_generation_budget(monkeypatch):
    monkeypatch.setattr(generation_limits.settings, "APP_ENV", "production")
    check = AsyncMock(return_value=[0, 42]); monkeypatch.setattr(generation_limits, "check_budget", check)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=generation_limits.GenerationLimits(response)), base_url="https://test") as client:
        assert (await client.post("/api/v1/pharma/analysis/stream")).status_code == 429
        assert (await client.get("/api/v1/pharma/updates")).status_code == 200
    check.assert_awaited_once()
