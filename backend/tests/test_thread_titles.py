import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from src.api.v1.search import TitleRequest, generate_title
from src.services.llm_service import GroqLLMService, groq_llm_service
from src.services.thread_titles import fallback_title, validate_title


class ThreadTitleTests(unittest.TestCase):
    def test_offline_titles_describe_topics_instead_of_copying_requests(self):
        cases = {
            "write a python code": "Python Coding",
            "hi corten": "New Conversation",
            "what's my previous question??": "Conversation Recap",
            "Remember that my project is Meridian.": "Meridian Project Notes",
            "how do I forecast pharma sales?": "Pharma Forecasting",
            "what is Chryselys?": "Chryselys Discussion",
        }
        for query, title in cases.items():
            with self.subTest(query=query):
                self.assertEqual(fallback_title(query), title)

    def test_invalid_headings_are_rejected(self):
        for value in [None, "", "Python", "x " * 40, "# Python Coding", "Python\nCoding",
                      "write a python code", "What Is Python", "https://test.invalid Python"]:
            with self.subTest(value=value):
                self.assertIsNone(validate_title(value, "write a python code"))
        self.assertEqual(validate_title('Title: "Python Coding Help"', "write a python code"), "Python Coding Help")

    def test_title_payload_is_bounded(self):
        with self.assertRaises(ValidationError):
            TitleRequest(query="x" * 16001)
        with self.assertRaises(ValidationError):
            TitleRequest(query="Python", answer="x" * 2001)


class ThreadTitleIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_has_room_for_reasoning_and_receives_bounded_topic_context(self):
        completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"title": "Python Coding Help"})))])
        create = AsyncMock(return_value=completion)
        service = GroqLLMService()
        service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self.assertEqual(await service.generate_thread_title("write a python code" + " " * 2000, "a" * 3000), "Python Coding Help")
        payload = create.call_args.kwargs
        self.assertGreaterEqual(payload["max_tokens"], 256)
        context = json.loads(payload["messages"][1]["content"])
        self.assertLessEqual(len(context["query"]), 1600)
        self.assertLessEqual(len(context["answer_excerpt"]), 1000)

    async def test_provider_failure_and_malformed_output_fall_back(self):
        service = GroqLLMService()
        for value in [None, "not json", '{"title":"write a python code"}', '[]', '{"title":null}']:
            create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))]))
            service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            self.assertEqual(await service.generate_thread_title("write a python code"), "Python Coding")
        service.client.chat.completions.create = AsyncMock(side_effect=TimeoutError())
        self.assertEqual(await service.generate_thread_title("write a python code"), "Python Coding")
        service.client = None
        self.assertEqual(await service.generate_thread_title("write a python code"), "Python Coding")

    async def test_endpoint_passes_answer_context_and_classifies_source(self):
        with patch.object(groq_llm_service, "generate_thread_title", AsyncMock(return_value="Python Coding Help")) as llm:
            result = await generate_title(TitleRequest(query="write a python code", answer="An example"))
        self.assertEqual(result, {"title": "Python Coding Help", "source": "generated"})
        llm.assert_awaited_once_with("write a python code", "An example")
        with patch.object(groq_llm_service, "generate_thread_title", AsyncMock(side_effect=RuntimeError())):
            self.assertEqual((await generate_title(TitleRequest(query="write a python code")))["title"], "Python Coding")

    async def test_greetings_and_conversation_recall_do_not_call_a_model(self):
        with patch.object(groq_llm_service, "generate_thread_title", AsyncMock()) as llm:
            self.assertEqual((await generate_title(TitleRequest(query="hi corten")))["title"], "New Conversation")
            self.assertEqual((await generate_title(TitleRequest(query="what's my previous question?")))["title"], "Conversation Recap")
        llm.assert_not_awaited()
