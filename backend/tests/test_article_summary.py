"""Discover summaries must be complete, bounded and safe to publish."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.services.article_summary import ArticleSummaryIncompleteError, complete_summary
from src.services.llm_runtime import LLMProviderError, LLMQuotaError
from src.services.llm_service import groq_llm_service


def response(content, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)])


class CompletionChecks(unittest.TestCase):
    def test_sentence_endings_allow_citations_quotes_and_non_latin_punctuation(self):
        for text in ["The trial finished. [1]", "A supported result. [1][2]", 'They said "finished." [2]',
                     "The study ended (as planned).", "The trial finished. **[1]**", "测试已经完成。[1]", "A supported result!"]:
            with self.subTest(text=text):
                self.assertEqual(complete_summary(text, "stop"), text)

    def test_unfinished_empty_or_excessively_long_drafts_are_rejected_without_trimming(self):
        for text, finish in [("The trial finished.", "length"), ("The trial finished.", None),
                             ("The next event is", "stop"), ("The next event... [1]", "stop"),
                             ("", "stop"), ("word " * 321 + ".", "stop")]:
            with self.subTest(text=text[:35], finish=finish):
                self.assertIsNone(complete_summary(text, finish))


class SummaryGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def generate(self, create):
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(groq_llm_service, "client", client):
            return "".join([part async for part in groq_llm_service.stream_article_summary(
                "A supplied study result", "The supplied study enrolled 40 people and completed in October.",
                [{"title": "Study result", "snippet": "40 people enrolled; study completed."}],
            )])

    async def test_complete_summary_is_published_whole_with_medium_length_instructions(self):
        text = "The supplied study enrolled 40 people and completed in October. [1]"
        create = AsyncMock(return_value=response(text))
        self.assertEqual(await self.generate(create), text)
        create.assert_awaited_once()
        self.assertFalse(create.call_args.kwargs["stream"])
        self.assertIn("180–260 words", str(create.call_args.kwargs["messages"]))

    async def test_length_limited_draft_is_replaced_once_not_appended_to_final_summary(self):
        text = "The study completed in October after enrolling 40 people. [1]"
        create = AsyncMock(side_effect=[response("DO_NOT_PUBLISH: The result was", "length"), response(text)])
        self.assertEqual(await self.generate(create), text)
        self.assertEqual(create.await_count, 2)
        retry_messages = create.call_args.kwargs["messages"]
        self.assertIn("120–180 words", retry_messages[-1]["content"])
        self.assertNotIn("DO_NOT_PUBLISH", str(retry_messages))

    async def test_stop_with_an_unfinished_sentence_is_also_regenerated(self):
        text = "The trial completed. [1]"
        create = AsyncMock(side_effect=[response("The next step is"), response(text)])
        self.assertEqual(await self.generate(create), text)
        self.assertEqual(create.await_count, 2)

    async def test_two_incomplete_attempts_raise_a_retryable_error_and_publish_no_text(self):
        create = AsyncMock(return_value=response("Incomplete draft", "length"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        published = []
        with patch.object(groq_llm_service, "client", client):
            with self.assertRaises(ArticleSummaryIncompleteError):
                async for part in groq_llm_service.stream_article_summary("Supplied story", "Evidence", []):
                    published.append(part)
        self.assertEqual(published, [])
        self.assertEqual(create.await_count, 2)

    async def test_provider_rejection_or_quota_does_not_start_regeneration_loops(self):
        create = AsyncMock(return_value=response(None, "content_filter"))
        with self.assertRaises(ArticleSummaryIncompleteError):
            await self.generate(create)
        create.assert_awaited_once()
        create = AsyncMock(side_effect=LLMQuotaError(3600))
        with self.assertRaises(LLMQuotaError):
            await self.generate(create)
        create.assert_awaited_once()

    async def test_missing_evidence_is_rejected_before_calling_the_provider(self):
        create = AsyncMock()
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.object(groq_llm_service, "client", client):
            with self.assertRaisesRegex(LLMProviderError, "not enough article text"):
                async for _ in groq_llm_service.stream_article_summary("Headline only", "", []):
                    self.fail("A headline alone must not produce a summary")
        create.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
