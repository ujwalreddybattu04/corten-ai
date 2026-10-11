"""Visible article source numbers must match the model's ordered evidence."""
import json
import unittest
from unittest.mock import AsyncMock, patch
from src.services.search_orchestrator import search_orchestrator
from src.services.web_search_service import tavily_search_service
from src.services.serper_image_service import serper_image_service
from src.services.llm_service import groq_llm_service


class ArticleCitationTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_article_is_numbered_consistently_and_deduplicated(self):
        captured = {}
        async def summary(**kwargs):
            captured.update(kwargs)
            yield "A supported result. [1]"
        source = {"title": "Context", "url": "https://source.example/context", "snippet": "Context evidence.", "domain": "source.example"}
        original = {"title": "Original", "url": "https://publisher.example/article", "snippet": "Search excerpt."}
        with patch.object(tavily_search_service, "extract", AsyncMock(return_value="Full original evidence.")), patch.object(tavily_search_service, "search", AsyncMock(return_value={"results": [source, original]})), patch.object(serper_image_service, "search_images", AsyncMock(return_value=[])), patch.object(groq_llm_service, "stream_article_summary", summary):
            events = [json.loads(line[6:]) async for line in search_orchestrator.stream_article_summary("Original", original["url"])]
        visible = next(event["sources"] for event in events if event["type"] == "sources")
        self.assertEqual([source["url"] for source in visible], [original["url"], source["url"]])
        self.assertEqual([source["url"] for source in visible], [source["url"] for source in captured["search_results"]])
        self.assertEqual([source["citationIndex"] for source in visible], [1, 2])

    async def test_followup_uses_previous_summary_as_context_without_shifting_citations(self):
        captured = {}
        async def followup(**kwargs):
            captured.update(kwargs)
            yield "A supported answer. [1]"
        source = {"title": "Evidence", "url": "https://source.example", "snippet": "Evidence.", "domain": "source.example"}
        with patch.object(tavily_search_service, "search", AsyncMock(return_value={"results": [source]})), patch.object(groq_llm_service, "stream_article_followup", followup):
            events = [json.loads(line[6:]) async for line in search_orchestrator.stream_article_summary("Article", "https://publisher.example", followup="Why?", previous_summary="A previous answer.")]
        self.assertEqual(captured["search_results"], [source])
        self.assertEqual(captured["previous_summary"], "A previous answer.")
        self.assertEqual(next(event["sources"][0]["url"] for event in events if event["type"] == "sources"), source["url"])
