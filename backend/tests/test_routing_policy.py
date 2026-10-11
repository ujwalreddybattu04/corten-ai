"""Routing boundaries and failure behavior, without calling external APIs."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.services.agents.routing_policy import direct_intent
from src.services.agents.smart_router import SmartRouter


class RoutingPolicyTests(unittest.TestCase):
    def test_offline_requests(self):
        cases = {
            "who developed you ??": "identity",
            "Who are you and who developed you?": "identity",
            "Please tell me who created Corten AI?": "identity",
            "Which company developed you?": "identity",
            "Who trained you?": "identity",
            "What can you do?": "identity",
            "Hello there!": "greeting",
            "Thank you so much": "greeting",
            "2 + 2": "math",
            "Calculate (12 * 4) / 3": "math",
            "sqrt(144)": "math",
            "Write a leave email for today": "creative",
            "Write a poem about the moon": "creative",
            "Write a Python function to reverse a string": "code",
            'Translate "latest news" into Telugu': "text",
            "Rewrite this: Our current prices are listed below.": "text",
            "Summarize this text: The latest market news is unavailable.": "text",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(direct_intent(query, "Corten"), expected)

    def test_external_and_mixed_requests_keep_search(self):
        cases = [
            "Who developed Python?",
            "Who created ChatGPT?",
            "Who is the CEO of Chryselys Private Limited?",
            "Who developed you and what is the current stock price?",
            "Who are you? Also search for AI news.",
            "Hi, latest AI news please",
            "What is Python?",
            "What is the weather today?",
            "Convert 100 USD to EUR at current exchange rates",
            "Write an article about the latest AI news",
            "Write a biography of Einstein",
            "Write code using the latest Next.js API",
            "Summarize https://example.com/article",
            "Find academic sources about photosynthesis",
            "What is the current medical dosage recommendation?",
        ]
        for query in cases:
            with self.subTest(query=query):
                self.assertIsNone(direct_intent(query, "Corten"))

    def test_transforming_previous_answer(self):
        self.assertEqual(direct_intent("Summarize your answer", "Corten", True), "text")
        self.assertIsNone(direct_intent("Summarize the latest news", "Corten", True))


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_bypasses_classifier_and_tools_in_every_focus(self):
        classifier = AsyncMock(side_effect=AssertionError("Identity should not call classifier"))
        with patch("src.services.llm_service.groq_llm_service.client", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=classifier))
        )):
            for focus in ["all", "academic", "writing", "math", "reddit"]:
                route = await SmartRouter().route("who developed you ??", focus)
                self.assertEqual(route["strategy"], "direct")
                self.assertFalse(route["requires_search"])
                self.assertEqual(route["tools"], [])
            classifier.assert_not_awaited()

    async def test_classifier_failure_keeps_unknown_requests_search_first(self):
        classifier = AsyncMock(side_effect=RuntimeError("Classifier unavailable"))
        with patch("src.services.llm_service.groq_llm_service.client", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=classifier))
        )):
            route = await SmartRouter().route("Who developed Python?")
        self.assertTrue(route["requires_search"])
        self.assertEqual(route["strategy"], "standard")
        self.assertIn("web_search", route["tools"])

    async def test_contradictory_strategy_normalizes_to_direct(self):
        payload = {"strategy": "quick", "query_type": "text", "requires_search": False}
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        classifier = AsyncMock(return_value=response)
        with patch("src.services.llm_service.groq_llm_service.client", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=classifier))
        )):
            route = await SmartRouter().route("Make the wording more formal", messages=[{"role":"user", "content":"Dear team, hi!"}])
        self.assertEqual(route["strategy"], "direct")
        self.assertEqual(route["tools"], [])
        self.assertIn("Conversation context", classifier.call_args.kwargs["messages"][1]["content"])

    async def test_current_facts_cannot_be_forced_offline_by_classifier(self):
        payload = {"strategy": "direct", "query_type": "creative", "requires_search": False}
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        classifier = AsyncMock(return_value=response)
        with patch("src.services.llm_service.groq_llm_service.client", SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=classifier))
        )):
            route = await SmartRouter().route("Write about the latest AI news", "writing")
        self.assertTrue(route["requires_search"])
        self.assertIn("web_search", route["tools"])

    async def test_identity_stream_never_executes_tools(self):
        from src.services.search_orchestrator import SearchOrchestrator

        async def answer(*args):
            yield "I am Corten, developed by Chryselys Private Limited."

        with patch("src.services.search_orchestrator.groq_llm_service.stream_answer", answer), \
             patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock()) as tools:
            chunks = [chunk async for chunk in SearchOrchestrator().stream_search("who developed you ??")]
        events = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in chunks]
        self.assertIn("token", [event["type"] for event in events])
        self.assertNotIn("sources", [event["type"] for event in events])
        self.assertNotIn("tools_selected", [event["type"] for event in events])
        tools.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
