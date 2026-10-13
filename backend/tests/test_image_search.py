"""Provider failures must not silently remove working fallback images."""
import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
from src.config.settings import settings
from src.services.serper_image_service import ImageSearchUnavailable, SerperImageService, normalized_images, public_image_url
from src.tools.base_tool import ToolContext, ToolStatus
from src.tools.media.image_search_tool import image_search_tool

HTTP_CLIENT = httpx.AsyncClient

@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setattr(settings, "SERPER_API_KEY", "fake-serper")
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "fake-tavily")

def transport(handler):
    return patch("src.services.serper_image_service.httpx.AsyncClient",
        lambda **kw: HTTP_CLIENT(transport=httpx.MockTransport(handler), **kw))

@pytest.mark.asyncio
async def test_rejected_primary_falls_back_and_caches_without_exposing_credentials(providers, caplog):
    seen = []
    def handle(request):
        seen.append(request)
        if request.url.host == "google.serper.dev":
            return httpx.Response(403, json={"message":"access denied"})
        body = json.loads(request.content)
        assert body["include_images"] and body["search_depth"]=="basic"
        assert request.headers["Authorization"]=="Bearer fake-tavily"
        return httpx.Response(200,json={"images":["https://images.example/fuji.jpg"],
            "results":[{"url":"https://source.example/fuji","title":"Fuji", "images":[{"url":"https://images.example/fuji.jpg"}]}]})
    service = SerperImageService()
    with transport(handle):
        images = await service.search_images("Mount Fuji",12)
        assert images[0]["sourceUrl"]=="https://source.example/fuji"
        images[0]["url"]="mutated"
        assert (await service.search_images("Mount Fuji",12))[0]["url"]=="https://images.example/fuji.jpg"
        await service.search_images("Different place",12)
    assert [r.url.host for r in seen]==["google.serper.dev","api.tavily.com","api.tavily.com"]
    assert "fake-serper" not in caplog.text and "fake-tavily" not in caplog.text

@pytest.mark.asyncio
async def test_tavily_only_configuration_keeps_tool_available(providers,monkeypatch):
    monkeypatch.setattr(settings,"SERPER_API_KEY","")
    assert await image_search_tool.health_check()==ToolStatus.HEALTHY
    with patch("src.services.serper_image_service.serper_image_service",SerperImageService()), transport(
        lambda req: httpx.Response(200,json={"images":[{"url":"https://images.example/diagram.png","description":"Diagram"}]})):
        result = await image_search_tool.execute(ToolContext(query="Diagram"))
    assert result.success and result.data["image_count"]==1

@pytest.mark.asyncio
async def test_empty_results_are_distinct_from_provider_failure(providers):
    with transport(lambda req: httpx.Response(200,json={"images":[]})):
        assert await SerperImageService().search_images("No matching images")==[]
    with transport(lambda req: httpx.Response(503,json={})):
        with pytest.raises(ImageSearchUnavailable):
            await SerperImageService().search_images("Unavailable")

@pytest.mark.asyncio
async def test_timeout_malformed_and_oversized_primary_responses_use_fallback(providers):
    for failure in ("timeout","invalid","oversized"):
        def handle(request):
            if request.url.host=="api.tavily.com":
                return httpx.Response(200,json={"images":["https://images.example/good.jpg"]})
            if failure=="timeout":raise httpx.ReadTimeout("timeout",request=request)
            if failure=="invalid":return httpx.Response(200,content=b"invalid-json")
            return httpx.Response(200,content=b"x"*(2*1024*1024+1))
        with transport(handle):
            assert len(await SerperImageService().search_images("Valid"))==1

@pytest.mark.asyncio
async def test_credential_change_rechecks_primary_and_cancellation_propagates(providers,monkeypatch):
    service = SerperImageService()
    def rejected(request):return httpx.Response(403,json={})
    with transport(rejected):
        with pytest.raises(ImageSearchUnavailable):await service.search_images("One")
    monkeypatch.setattr(settings,"SERPER_API_KEY","new-fake-serper")
    async def cancelled(request):raise asyncio.CancelledError()
    with transport(cancelled):
        with pytest.raises(asyncio.CancelledError):await service.search_images("Two")

def test_normalization_bounds_deduplicates_and_preserves_actual_source():
    data={"images":[None,{"url":"javascript:alert(1)"},"https://images.example/a.jpg","https://images.example/a.jpg"],
          "results":[{"url":"https://source.example/article","title":"Original title","images":[{"url":"https://images.example/a.jpg"}]}]}
    images=normalized_images(data,"tavily","Query",1)
    assert len(images)==1 and images[0]["alt"]=="Original title"
    assert images[0]["sourceUrl"]=="https://source.example/article"
    for bad in ("http://images.example/a.jpg","https://127.0.0.1/a.jpg","https://10.0.0.1/a.jpg","https://user:pass@images.example/a.jpg","https://host.local/a.jpg","https://bad.example:garbage/a.jpg"):
        assert public_image_url(bad)==""

@pytest.mark.asyncio
async def test_no_keys_or_blank_query_makes_no_requests(providers,monkeypatch):
    with transport(lambda req: pytest.fail("Unexpected provider request")):
        assert await SerperImageService().search_images("  ")==[]
        monkeypatch.setattr(settings,"SERPER_API_KEY","")
        monkeypatch.setattr(settings,"TAVILY_API_KEY","")
        assert await SerperImageService().search_images("Query")==[]
        assert await image_search_tool.health_check()==ToolStatus.DOWN
