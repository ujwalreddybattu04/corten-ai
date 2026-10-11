"""Provider fallback, truthful errors, and pagination/cache regressions without live APIs."""
import unittest
import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from src.api.v1.discover import router
from src.services import discover_service as service


NEWS = {"status": "ok", "articles": [{"title": "Research update", "url": "https://example.com/research",
    "source": {"name": "Example News"}, "publishedAt": "2026-10-11T12:00:00Z"}]}
GUARDIAN = {"response": {"status": "ok", "currentPage": 1, "pages": 2, "total": 2,
    "results": [{"webTitle": "Research update", "webUrl": "https://example.com/research"}]}}
RSS = '''<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>New discovery</title><link>https://www.bbc.com/news/research</link>
<description>Research &amp; development</description><pubDate>Sun, 11 Oct 2026 12:00:00 GMT</pubDate>
<media:thumbnail url="https://ichef.bbci.co.uk/image.jpg"/></item></channel></rss>'''


class DiscoverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for state in (service._news_memory, service._news_pending, service._news_retry_at, service._provider_retry_at):
            state.clear()
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
        return httpx.Response(status, text=payload) if isinstance(payload, str) else httpx.Response(status, json=payload)

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
        result = await service.get_news_articles("top", 2, 20)
        self.assertEqual(result["status"], "empty")
        self.assertFalse(result["has_more"])
        self.assertEqual(len(self.requests), 1)

    async def test_successful_empty_response_is_not_a_provider_failure(self):
        self.responses = {"newsapi.org": (200, {"status": "ok", "articles": []})}
        result = await service.get_news_articles()
        self.assertEqual(result["status"], "empty")
        self.assertEqual((await service.get_news_articles())["status"], "empty")
        self.write_cache.assert_not_awaited()

    async def test_cache_shares_page_sizes_without_skipping_or_repeating_stories(self):
        entries = [{**NEWS["articles"][0], "url": f"https://example.com/{i}"} for i in range(20)]
        self.responses = {"newsapi.org": (200, {"status": "ok", "articles": entries})}
        first = await service.get_news_articles("business", 1, 6)
        second = await service.get_news_articles("business", 2, 6)
        large = await service.get_news_articles("business", 1, 18)
        self.assertEqual([a["url"] for a in first["articles"]], [f"https://example.com/{i}" for i in range(6)])
        self.assertEqual([a["url"] for a in second["articles"]], [f"https://example.com/{i}" for i in range(6, 12)])
        self.assertEqual(len(large["articles"]), 18)
        self.assertEqual(len([r for r in self.requests if r.url.host == "newsapi.org"]), 1)
        self.assertEqual(self.requests[-1].url.params["pageSize"], "20")
        self.write_cache.assert_awaited_once()

    async def test_redis_cache_survives_process_memory_loss(self):
        self.responses = {"newsapi.org": (200, NEWS)}
        await service.get_news_articles("business", 1, 6)
        cached = self.write_cache.await_args.args[1]
        service._news_memory.clear()
        self.read_cache.return_value = cached
        self.requests.clear()
        self.assertEqual((await service.get_news_articles("business", 1, 6))["articles"], cached["articles"])
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
            self.assertEqual(response.headers["retry-after"], "30")
            self.responses = {"newsapi.org": (200, NEWS)}
            with patch.object(service.time, "time", return_value=time.time() + 31):
                self.assertEqual((await client.get("/discover?category=top")).status_code, 200)
            self.assertEqual((await client.get("/discover?category=unknown")).status_code, 422)

    async def test_http_failure_log_does_not_include_api_key(self):
        self.responses = {"newsapi.org": (401, {"message": "test-only-provider-key"})}
        with self.assertLogs(service.logger, level="WARNING") as logs:
            await service.get_news_articles()
        self.assertNotIn("test-only-provider-key", " ".join(logs.output))

    async def test_rss_fallback_works_without_provider_credentials(self):
        self.responses = {"feeds.bbci.co.uk": (200, RSS)}
        with patch.object(service.settings, "GUARDIAN_API_KEY", ""), patch.object(service.settings, "NEWSAPI_KEY", ""):
            result = await service.get_news_articles("top")
        self.assertEqual(result["provider"], "bbc-rss")
        self.assertEqual(result["articles"][0]["source"]["name"], "BBC News")
        self.assertEqual(result["articles"][0]["description"], "Research & development")
        self.assertEqual(result["articles"][0]["publishedAt"], "2026-10-11T12:00:00+00:00")
        self.assertFalse(result["has_more"])

    async def test_rss_rejects_xml_entities_and_invalid_links(self):
        self.responses = {"feeds.bbci.co.uk": (200, '<!DOCTYPE rss [<!ENTITY x "boom">]><rss><channel/></rss>')}
        self.assertEqual((await service.get_news_articles("top"))["status"], "unavailable")
        service._news_retry_at.clear()
        service._provider_retry_at.clear()
        self.responses = {"feeds.bbci.co.uk": (200, RSS.replace("https://www.bbc.com/news/research", "javascript:alert(1)"))}
        self.assertEqual((await service.get_news_articles("top"))["articles"], [])

    async def test_stale_stories_survive_outage_but_do_not_extend_age(self):
        self.responses = {"newsapi.org": (200, NEWS)}
        fresh = await service.get_news_articles("top", 1, 6)
        self.responses = {}
        with patch.object(service.time, "time", return_value=time.time() + service.NEWS_CACHE_TTL + 1):
            stale = await service.get_news_articles("top", 1, 6)
            requests = len(self.requests)
            again = await service.get_news_articles("top", 1, 6)
            self.assertEqual(len(self.requests), requests)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(again["fetched_at"], fresh["fetched_at"])
        self.assertEqual(stale["articles"], fresh["articles"])
        with patch.object(service.time, "time", return_value=time.time() + service.NEWS_STALE_TTL + 1):
            self.assertEqual((await service.get_news_articles("top", 1, 6))["status"], "unavailable")

    async def test_duplicate_requests_share_one_provider_fetch(self):
        self.responses = {"content.guardianapis.com": (200, GUARDIAN)}
        results = await asyncio.gather(*[service.get_news_articles("technology", 1, size) for size in (6, 10, 18, 20)])
        self.assertTrue(all(r["status"] == "available" for r in results))
        self.assertEqual(len(self.requests), 1)

    async def test_invalid_key_is_cooled_down_across_categories(self):
        self.responses = {"content.guardianapis.com": (401, {}), "newsapi.org": (200, NEWS)}
        await service.get_news_articles("top", 1, 6)
        await service.get_news_articles("business", 1, 6)
        self.assertEqual(len([r for r in self.requests if r.url.host == "content.guardianapis.com"]), 1)
        self.responses["content.guardianapis.com"] = (200, GUARDIAN)
        with patch.object(service.settings, "GUARDIAN_API_KEY", "new-test-key"):
            result = await service._fetch_guardian(self.real_client(transport=httpx.MockTransport(self.handle)), "top", 1, 20)
        self.assertEqual(result["provider"], "guardian")

    async def test_cache_failure_does_not_prevent_live_or_memory_feed(self):
        self.read_cache.side_effect = OSError("offline")
        self.write_cache.side_effect = OSError("offline")
        self.responses = {"feeds.bbci.co.uk": (200, RSS)}
        first = await service.get_news_articles("top", 1, 6)
        requests = len(self.requests)
        second = await service.get_news_articles("top", 1, 6)
        self.assertEqual(first["articles"], second["articles"])
        self.assertEqual(len(self.requests), requests)

    async def test_bad_cache_and_invalid_provider_links_trigger_live_fallback(self):
        self.read_cache.return_value = {"status": "available", "articles": [], "fetched_at_epoch": "bad"}
        self.responses = {"newsapi.org": (200, {"status": "ok", "articles": [{**NEWS["articles"][0], "url": "javascript:alert(1)"}]}),
                          "feeds.bbci.co.uk": (200, RSS)}
        result = await service.get_news_articles("top", 1, 6)
        self.assertEqual(result["provider"], "bbc-rss")
        self.assertTrue(result["articles"])

    async def test_page_crossing_canonical_pool_boundary_keeps_correct_order(self):
        original = self.handle
        def paginated(request):
            if request.url.host != "content.guardianapis.com":
                return original(request)
            self.requests.append(request)
            page = int(request.url.params["page"])
            start = (page - 1) * 20
            return httpx.Response(200, json={"response": {"status": "ok", "currentPage": page, "pages": 2,
                "results": [{"webTitle": f"Story {i}", "webUrl": f"https://example.com/{i}"} for i in range(start, start + 20)]}})
        self.handle = paginated
        first = await service.get_news_articles("top", 1, 18)
        second = await service.get_news_articles("top", 2, 18)
        self.assertEqual([a["url"] for a in first["articles"] + second["articles"]], [f"https://example.com/{i}" for i in range(36)])
        self.assertEqual(len(self.requests), 2)

    async def test_cancelling_one_reader_does_not_cancel_shared_news_refresh(self):
        gate = asyncio.Event()
        self.responses = {"feeds.bbci.co.uk": (200, RSS)}
        original = service._fetch_rss
        async def delayed(*args):
            await gate.wait()
            return await original(*args)
        with patch.object(service, "_fetch_rss", delayed):
            one = asyncio.create_task(service.get_news_articles("top", 1, 6))
            two = asyncio.create_task(service.get_news_articles("top", 1, 6))
            await asyncio.sleep(0.01)
            one.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await one
            gate.set()
            self.assertEqual((await two)["status"], "available")
        self.assertEqual(len([r for r in self.requests if r.url.host == "feeds.bbci.co.uk"]), 1)


if __name__ == "__main__":
    unittest.main()
