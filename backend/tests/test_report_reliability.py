"""Failed or incomplete research must never become a successful PDF."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pypdf import PdfReader
from src.services.llm_runtime import LLMProviderError, LLMQuotaError
from src.services.report_service import ReportService, REPORT_TTL_SECONDS
from src.services.llm_service import groq_llm_service

SOURCE = {"title": "R&D <results>", "url": "https://example.com/study?a=1&b=2", "domain": "example.com", "snippet": "The study finished."}
DRAFT = {"title": "R&D <review>", "subtitle": "Evidence & limitations", "executive_summary": "The study finished. [1]", "sections": [{"title": "Findings & context", "content": "A supported finding. [1]"}]}

def reply(data, finish="stop"):
    text = json.dumps(data) if isinstance(data, dict) else data
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)])

def client(create):
    return SimpleNamespace(client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))

class ReportReliability(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = ReportService()

    async def test_quota_stops_the_only_model_request_without_placeholder_content(self):
        create = AsyncMock(side_effect=LLMQuotaError(60))
        with self.assertRaises(LLMQuotaError):
            await self.service._draft_report(client(create), "Topic", [SOURCE])
        create.assert_awaited_once()

    async def test_incomplete_or_malformed_drafts_are_rejected(self):
        for response in [reply(DRAFT, "length"), reply(None), reply("not JSON"), reply({**DRAFT, "executive_summary": "The next stage is"}), reply({**DRAFT, "sections": []})]:
            with self.subTest(response=response), self.assertRaises(LLMProviderError):
                await self.service._draft_report(client(AsyncMock(return_value=response)), "Topic", [SOURCE])

    async def test_valid_draft_is_preserved_in_one_model_request(self):
        create = AsyncMock(return_value=reply(DRAFT))
        result = await self.service._draft_report(client(create), "Topic", [SOURCE])
        self.assertEqual(result, DRAFT)
        create.assert_awaited_once()

    async def test_unknown_citations_are_rejected(self):
        draft = {**DRAFT, "executive_summary": "Unsupported source. [2]"}
        with self.assertRaises(LLMProviderError):
            await self.service._draft_report(client(AsyncMock(return_value=reply(draft))), "Topic", [SOURCE])

    async def test_no_research_evidence_produces_error_without_success(self):
        from src.services.web_search_service import tavily_search_service
        draft = AsyncMock()
        with patch.object(groq_llm_service, "client", object()), patch.object(self.service, "_draft_report", draft), patch.object(tavily_search_service, "search", AsyncMock(return_value={"results": []})):
            events = [json.loads(line[6:]) async for line in self.service.stream_report("Topic")]
        self.assertIn("error", [event["type"] for event in events])
        self.assertNotIn("report_complete", [event["type"] for event in events])
        draft.assert_not_awaited()

    async def test_complete_pipeline_creates_a_real_pdf_and_download_path(self):
        from src.services.web_search_service import tavily_search_service
        with tempfile.TemporaryDirectory() as directory, patch.object(groq_llm_service, "client", object()), patch("src.services.report_service.REPORTS_DIR", directory), patch.object(tavily_search_service, "search", AsyncMock(return_value={"results": [SOURCE]})), patch.object(self.service, "_draft_report", AsyncMock(return_value=DRAFT)):
            events = [json.loads(line[6:]) async for line in self.service.stream_report("Topic")]
            complete = next(event for event in events if event["type"] == "report_complete")
            report_id = events[0]["report_id"]
            self.assertRegex(report_id, r"^[a-f0-9]{32}$")
            path = self.service.get_report_path(report_id)
            self.assertTrue(Path(path).read_bytes().startswith(b"%PDF"))
            text = " ".join(page.extract_text() for page in PdfReader(path).pages)
            self.assertIn("R&D <review>", text)
            self.assertIn("A supported finding.", text)
            self.assertGreaterEqual(complete["pages"], 1)
            os.utime(path, (time.time() - REPORT_TTL_SECONDS - 1,) * 2)
            self.assertIsNone(self.service.get_report_path(report_id))
            self.assertIsNone(self.service.get_report_path("../private"))
