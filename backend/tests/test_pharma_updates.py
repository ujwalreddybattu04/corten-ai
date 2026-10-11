"""Deterministic provider, cache, failure, and endpoint checks; no external calls."""
import asyncio
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
    def test_fda_filters_each_nested_submission_not_entire_application(self):
        payload = {"results": [{"application_number": "NDA123456", "products": [{"brand_name": "Example"}],
            "submissions": [
                {"submission_status": "AP", "submission_status_date": "20261008", "submission_type": "SUPPL", "submission_number": "003"},
                {"submission_status": "AP", "submission_status_date": "20200101"},
                {"submission_status": "TA", "submission_status_date": "20261009"},
                {"submission_status": "AP", "submission_status_date": "20261020"},
            ]}]}
        items = normalize_fda(payload, "2026-10-01", "2026-10-09")
        self.assertEqual(len(items), 1)
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
            "items": [{"id": f"{source}:example", "date": today}]}

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
        previous = service._cache[("all", 7)][1]
        service._cache[("all", 7)] = (0, previous)
        async def failing(client, source, *args):
            if source == "fda": raise httpx.ConnectError("Provider offline")
            return self.source_result(source)
        service._source = AsyncMock(side_effect=failing)
        feed = await service.get_feed()
        self.assertEqual(feed["sources"][0]["status"], "stale")
        self.assertEqual(len(feed["items"]), 3)
        previous = service._cache[("all", 7)][1]
        previous["sources"][0]["checked_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        service._cache[("all", 7)] = (0, previous)
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
        client.get.assert_not_awaited()

    async def test_fda_no_matches_is_empty_not_failure(self):
        client = AsyncMock()
        client.get.return_value = httpx.Response(404, json={"error": {"code": "NOT_FOUND"}}, request=httpx.Request("GET", "https://api.fda.gov"))
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
                self.assertEqual(response.headers["cache-control"], "no-store")
                get_feed.assert_awaited_once_with(topic="oncology", days=30)


if __name__ == "__main__":
    unittest.main()
