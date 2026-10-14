"""Deterministic provider, cache, failure, and endpoint checks; no external calls."""
import asyncio
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from src.api.v1.pharma import router
from src.services.pharma_updates import (
    PharmaUpdatesService, SOURCES, clean_text, normalize_fda,
    normalize_news, normalize_trials,
)


class NormalizationTests(unittest.TestCase):
    def test_optional_news_thumbnails_cannot_inject_untrusted_image_hosts(self):
        article = {"webPublicationDate": "2026-10-10T12:00:00Z", "webUrl": "https://www.theguardian.com/science/example", "webTitle": "Pharma evidence", "fields": {"thumbnail": "https://i.guim.co.uk/img/media/example.jpg"}}
        data = {"response": {"results": [article]}}
        self.assertEqual(normalize_news(data, "2026-10-01", "2026-10-12")[0]["thumbnail"], article["fields"]["thumbnail"])
        for thumbnail in ["https://127.0.0.1/image", "http://i.guim.co.uk/image", "https://user:password@i.guim.co.uk/image", "https://i.guim.co.uk.evil.test/image", "https://i.guim.co.uk:invalid/image", None]:
            article["fields"]["thumbnail"] = thumbnail
            self.assertNotIn("thumbnail", normalize_news(data, "2026-10-01", "2026-10-12")[0])
        article["fields"] = None
        self.assertEqual(len(normalize_news(data, "2026-10-01", "2026-10-12")), 1)

    def test_fda_filters_each_nested_submission_not_entire_application(self):
        payload = {"results": [{"application_number": "NDA123456", "products": [{"brand_name": "Example"}],
            "submissions": [
                {"submission_status": "AP", "submission_status_date": "20261008", "submission_type": "SUPPL", "submission_number": "003"},
                {"submission_status": "AP", "submission_status_date": "20200101"},
                {"submission_status": "TA", "submission_status_date": "20261009"},
                {"submission_status": "AP", "submission_status_date": "20261020"},
            ]}]}
        items = normalize_fda(payload, "2026-10-01", "2026-10-09")
        self.assertEqual(len(items), 2)
        self.assertIn('tentative approval',items[1]['title'])
        self.assertEqual(items[1]['details']['approval_status'],'tentative')
        self.assertEqual(items[0]["date"], "2026-10-08")
        self.assertIn("supplemental approval", items[0]["title"])
        self.assertIn("ApplNo=123456", items[0]["url"])

    def test_trials_excludes_non_drug_records_and_invalid_ids(self):
        def study(nct, intervention):
            return {"protocolSection": {
                "identificationModule": {"nctId": nct, "briefTitle": "Example study"},
                "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-10-08"}, "overallStatus": "RECRUITING"},
                "armsInterventionsModule": {"interventions": [{"type": intervention}]},
            }}
        items = normalize_trials({"studies": [study("NCT12345678", "DRUG"), study("NCT22222222", "DEVICE"), study("bad", "BIOLOGICAL")]}, "2026-10-01", "2026-10-09")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["date_label"], "Record updated")

    def test_news_rejects_unsafe_links_and_future_dates(self):
        def article(url, published):
            return {"webTitle": "Example headline", "webUrl": url, "webPublicationDate": published,
                "fields": {"trailText": "<p>Research &amp; <strong>development</strong></p>"}}
        items = normalize_news({"response": {"results": [article("https://example.com/news", "2026-10-08T08:00:00Z"), article("javascript:alert(1)", "2026-10-08"), article("https://example.com/future", "2026-11-01")]}}, "2026-10-01", "2026-10-09")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["summary"], "Research & development")
        self.assertEqual(clean_text("  <b>Short</b>   text", 8), "Short te")


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def source_result(self, source):
        today = datetime.now(timezone.utc).date().isoformat()
        return {"id": source, **SOURCES[source], "status": "available", "checked_at": datetime.now(timezone.utc).isoformat(), "source_updated_at": None,
            "items": [{"id": f"{source}:example", "source": source, "date": today}], "limited": False}

    async def test_coalesces_concurrent_calls_and_does_not_share_mutable_results(self):
        service = PharmaUpdatesService()
        async def provider(client, source, *args):
            await asyncio.sleep(0.01)
            return self.source_result(source)
        service._source = AsyncMock(side_effect=provider)
        first, second = await asyncio.gather(service.get_feed(), service.get_feed())
        self.assertEqual(service._source.await_count, 3)
        first["items"].clear()
        self.assertEqual(len(second["items"]), 3)
        self.assertEqual(len((await service.get_feed())["items"]), 3)

    async def test_partial_failure_reuses_recent_data_and_expires_after_24_hours(self):
        service = PharmaUpdatesService()
        async def provider(client, source, *args):
            return self.source_result(source)
        service._source = AsyncMock(side_effect=provider)
        await service.get_feed()
        previous = service._cache[("fda", "all", 7)]
        previous["retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        original_time = previous["value"]["checked_at"]
        async def failing(client, source, *args):
            if source == "fda": raise httpx.ConnectError("Provider offline")
            return self.source_result(source)
        service._source = AsyncMock(side_effect=failing)
        feed = await service.get_feed()
        self.assertEqual(feed["sources"][0]["status"], "stale")
        self.assertEqual(len(feed["items"]), 3)
        self.assertEqual(feed["sources"][0]["checked_at"], original_time)
        previous = service._cache[("fda", "all", 7)]
        previous["value"]["checked_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        previous["retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        feed = await service.get_feed()
        self.assertEqual(feed["sources"][0]["status"], "unavailable")
        self.assertEqual(len(feed["items"]), 2)

    async def test_provider_access_denied_is_explicit_without_losing_other_sources(self):
        service = PharmaUpdatesService()
        async def provider(client, source, *args):
            if source == "news":
                response = httpx.Response(401, request=httpx.Request("GET", "https://example.com"))
                response.raise_for_status()
            return self.source_result(source)
        service._source = AsyncMock(side_effect=provider)
        feed = await service.get_feed()
        self.assertEqual(feed["sources"][2]["status"], "authentication_required")
        self.assertEqual(len(feed["items"]), 2)

    async def test_unconfigured_news_skips_http(self):
        client = AsyncMock()
        with patch("src.services.pharma_updates.settings.GUARDIAN_API_KEY", ""):
            result = await PharmaUpdatesService()._source(client, "news", "all", "2026-10-01", "2026-10-09")
        self.assertEqual(result["status"], "unconfigured")
        client.stream.assert_not_called()

    async def test_fda_no_matches_is_empty_not_failure(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(404, json={"error": {"code": "NOT_FOUND"}}))
        async with httpx.AsyncClient(transport=transport) as client:
            result = await PharmaUpdatesService()._source(client, "fda", "all", "2026-10-01", "2026-10-09")
        self.assertEqual(result["status"], "empty")

    async def test_endpoint_validates_before_provider_requests(self):
        app = FastAPI(); app.include_router(router, prefix="/pharma")
        with patch("src.api.v1.pharma.pharma_updates_service.get_feed", new=AsyncMock(return_value={"items": []})) as get_feed:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for query in ("days=8", "days=invalid", "topic=unknown", "days=-1"):
                    self.assertEqual((await client.get("/pharma/updates?" + query)).status_code, 422)
                get_feed.assert_not_awaited()
                response = await client.get("/pharma/updates?days=30&topic=oncology")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "private, no-store")
                get_feed.assert_awaited_once_with(topic="oncology", days=30)

    async def test_fda_is_shared_across_therapy_filters(self):
        service = PharmaUpdatesService()
        service._source = AsyncMock(side_effect=lambda client, source, *args: self.source_result(source))
        await asyncio.gather(*(service.get_feed(topic=topic) for topic in ("all", "oncology", "cns")))
        self.assertEqual(sum(call.args[1] == "fda" for call in service._source.await_args_list), 1)
        self.assertEqual(service._source.await_count, 7)

    async def test_cancellation_does_not_cancel_shared_refresh(self):
        service = PharmaUpdatesService()
        gate = asyncio.Event()
        async def provider(client, source, *args):
            await gate.wait()
            return self.source_result(source)
        service._source = AsyncMock(side_effect=provider)
        first = asyncio.create_task(service.get_feed())
        second = asyncio.create_task(service.get_feed())
        await asyncio.sleep(0.02)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError): await first
        gate.set()
        self.assertEqual(len((await second)["items"]), 3)
        self.assertEqual(service._source.await_count, 3)
        self.assertEqual(len((await service.get_feed())["items"]), 3)

    async def test_provider_rate_limit_cooldown_applies_to_other_filters(self):
        service = PharmaUpdatesService()
        async def provider(client, source, *args):
            if source == "trials":
                httpx.Response(429, headers={"Retry-After": "7200"}, request=httpx.Request("GET", "https://clinicaltrials.gov")).raise_for_status()
            return self.source_result(source)
        service._source = AsyncMock(side_effect=provider)
        await service.get_feed()
        feed = await service.get_feed(topic="oncology", days=30)
        self.assertEqual(sum(call.args[1] == "trials" for call in service._source.await_args_list), 1)
        self.assertEqual(feed["sources"][1]["status"], "unavailable")
        self.assertGreater((datetime.fromisoformat(service._cooldowns["trials"]["until"]) - datetime.now(timezone.utc)).total_seconds(), 7190)

    async def test_malformed_and_oversized_provider_payloads_are_unavailable(self):
        for body in (b'{"unexpected":[]}', b' ' * 2_000_001):
            with self.subTest(size=len(body)):
                factory = lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)), **kwargs)
                with patch("src.services.pharma_updates.settings.GUARDIAN_API_KEY", ""):
                    feed = await PharmaUpdatesService(client_factory=factory).get_feed()
                self.assertEqual(feed["status"], "unavailable")
                self.assertEqual(feed["items"], [])

    async def test_complete_failure_returns_retryable_503(self):
        app = FastAPI(); app.include_router(router, prefix="/pharma")
        with patch("src.api.v1.pharma.pharma_updates_service.get_feed", new=AsyncMock(return_value={"status": "unavailable"})):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/pharma/updates")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers["retry-after"], "60")
                self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_shared_cache_coalesces_across_workers_and_reuses_snapshot(self):
        class Shared:
            def __init__(self): self.values = {}; self.leases = {}
            async def get(self, key): return copy.deepcopy(self.values.get(key))
            async def set(self, key, value, ttl): self.values[key] = copy.deepcopy(value)
            async def acquire(self, key, token):
                if key in self.leases: return False
                self.leases[key] = token; return True
            async def release(self, key, token):
                if self.leases.get(key) == token: self.leases.pop(key)
        cache = Shared()
        first = PharmaUpdatesService(shared_cache=cache)
        second = PharmaUpdatesService(shared_cache=cache)
        async def provider(client, source, *args):
            await asyncio.sleep(0.02)
            return self.source_result(source)
        first._source = AsyncMock(side_effect=provider)
        second._source = AsyncMock(side_effect=provider)
        a, b = await asyncio.gather(first.get_feed(), second.get_feed())
        self.assertEqual(first._source.await_count + second._source.await_count, 3)
        self.assertEqual(a["items"], b["items"])
        self.assertEqual(cache.leases, {})
        third = PharmaUpdatesService(shared_cache=cache)
        third._source = AsyncMock(side_effect=AssertionError("Must read shared data"))
        self.assertEqual(len((await third.get_feed())["items"]), 3)
        third._source.assert_not_awaited()

    async def test_100_readers_use_one_refresh_and_cache_cardinality_is_bounded(self):
        service = PharmaUpdatesService()
        service._source = AsyncMock(side_effect=lambda client, source, *args: self.source_result(source))
        feeds = await asyncio.gather(*(service.get_feed() for _ in range(100)))
        self.assertEqual(service._source.await_count, 3)
        self.assertTrue(all(len(feed["items"]) == 3 for feed in feeds))
        with self.assertRaises(ValueError): await service.get_feed(topic="unbounded-user-query")
        self.assertEqual(len(service._cache), 3)


if __name__ == "__main__":
    unittest.main()
