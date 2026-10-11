"""Provider fallback, truthful errors, and pagination/cache regressions without live APIs."""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from src.api.v1.discover import router
from src.services import discover_service as service


NEWS = {"status": "ok", "articles": [{"title": "Research update", "url": "https://example.com/research",
    "source": {"name": "Example News"}, "publishedAt": "2026-10-11T12:00:00Z"}]}
GUARDIAN = {"response": {"status": "ok", "currentPage": 1, "pages": 2, "total": 2,
    "results": [{"webTitle": "Research update", "webUrl": "https://example.com/research"}]}}


class DiscoverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.responses = {}
        self.read_cache = AsyncMock(return_value=None)
        self.write_cache = AsyncMock()
        for target, replacement in [("cache_get", self.read_cache), ("cache_set", self.write_cache)]:
            patcher = patch.object(service, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        for key in ("GUARDIAN_API_KEY", "NEWSAPI_KEY"):
            patcher = patch.object(service.settings, key, "test-only-provider-key")
            patcher.start()
            self.addCleanup(patcher.stop)
        self.real_client = httpx.AsyncClient
        patcher = patch.object(service.httpx, "AsyncClient", side_effect=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def client(self, **kwargs):
        return self.real_client(transport=httpx.MockTransport(self.handle), **kwargs)

    def handle(self, request):
        self.requests.append(request)
        status, payload = self.responses.get(request.url.host, (503, {}))
        return httpx.Response(status, json=payload)

    async def test_guardian_unauthorized_falls_back_to_newsapi_and_caches(self):
        self.responses = {"content.guardianapis.com": (401, {}), "newsapi.org": (200, NEWS)}
        result = await service.get_news_articles("top", 1, 18)
        self.assertEqual(result["provider"], "newsapi")
        self.assertEqual(result["articles"][0]["source"]["name"], "Example News")
        self.write_cache.assert_awaited_once()
        self.assertEqual(self.requests[-1].headers["X-Api-Key"], "test-only-provider-key")
        self.assertNotIn("apiKey", self.requests[-1].url.params)

    async def test_healthy_guardian_does_not_call_fallback(self):
        self.responses = {"content.guardianapis.com": (200, GUARDIAN)}
        result = await service.get_news_articles("technology")
        self.assertEqual(result["provider"], "guardian")
        self.assertEqual(len(self.requests), 1)

    async def test_missing_guardian_key_uses_newsapi_without_requesting_guardian(self):
        with patch.object(service.settings, "GUARDIAN_API_KEY", ""):
            self.responses = {"newsapi.org": (200, NEWS)}
            result = await service.get_news_articles()
        self.assertEqual(result["status"], "available")
        self.assertEqual([r.url.host for r in self.requests], ["newsapi.org"])

    async def test_all_failures_are_unavailable_and_not_cached(self):
        result = await service.get_news_articles()
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["has_more"])
        self.write_cache.assert_not_awaited()

    async def test_empty_first_page_tries_fallback_but_last_page_stays_empty(self):
        empty = {"response": {"status": "ok", "currentPage": 2, "pages": 2, "results": []}}
        self.responses = {"content.guardianapis.com": (200, empty), "newsapi.org": (200, NEWS)}
        self.assertEqual((await service.get_news_articles("top", 1))["provider"], "newsapi")
        self.requests.clear()
        result = await service.get_news_articles("top", 2)
        self.assertEqual(result["status"], "empty")
        self.assertFalse(result["has_more"])
        self.assertEqual(len(self.requests), 1)

    async def test_successful_empty_response_is_not_a_provider_failure(self):
        self.responses = {"newsapi.org": (200, {"status": "ok", "articles": []})}
        result = await service.get_news_articles()
        self.assertEqual(result["status"], "empty")
        self.write_cache.assert_not_awaited()

    async def test_cache_separates_page_sizes_and_serves_cached_results(self):
        self.responses = {"newsapi.org": (200, NEWS)}
        await service.get_news_articles("business", 1, 6)
        await service.get_news_articles("business", 1, 18)
        keys = [call.args[0] for call in self.read_cache.await_args_list]
        self.assertNotEqual(keys[0], keys[1])
        self.read_cache.return_value = {"status": "available", "articles": [1]}
        self.requests.clear()
        self.assertEqual((await service.get_news_articles())["articles"], [1])
        self.assertEqual(self.requests, [])

    async def test_legacy_entertainment_tab_ids_use_correct_newsapi_topics(self):
        self.responses = {"newsapi.org": (200, NEWS)}
        await service.get_news_articles("health")
        self.assertEqual(self.requests[-1].url.params["category"], "entertainment")
        await service.get_news_articles("entertainment")
        self.assertEqual(self.requests[-1].url.path, "/v2/everything")
        self.assertEqual(self.requests[-1].url.params["q"], "arts culture")

    async def test_endpoint_returns_503_on_source_failure_and_200_on_success(self):
        app = FastAPI()
        app.include_router(router, prefix="/discover")
        async with self.real_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/discover?category=top")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["status"], "unavailable")
            self.responses = {"newsapi.org": (200, NEWS)}
            self.assertEqual((await client.get("/discover?category=top")).status_code, 200)

    async def test_http_failure_log_does_not_include_api_key(self):
        self.responses = {"newsapi.org": (401, {"message": "test-only-provider-key"})}
        with self.assertLogs(service.logger, level="WARNING") as logs:
            await service.get_news_articles()
        self.assertNotIn("test-only-provider-key", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
