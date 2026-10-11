"""Conversation retrieval, routing boundaries and bounded long-chat context."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.services.conversation_memory import (
    MAX_HISTORY_CHARS, MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS, MISSING_HISTORY,
    answer_context, clean_history, conversation_intent, recall_answer,
)
from src.services.agents.smart_router import SmartRouter
from src.services.search_orchestrator import SearchOrchestrator
from src.services.llm_service import groq_llm_service


HISTORY = [
    {"role": "user", "content": "Who created the Look What I Can Do sketch?"},
    {"role": "assistant", "content": "An earlier answer."},
    {"role": "user", "content": "What project country did I mention?"},
    {"role": "assistant", "content": "India."},
]


class MemoryPolicyTests(unittest.TestCase):
    def test_recall_variants_are_conversation_only(self):
        for query in ["whats my previous question ??", "What was my last question?",
                      "What did I ask you earlier?", "Repeat my last message",
                      "Can you show me my first question?", "List my last 5 questions",
                      "What was my question before this?", "What was my 2nd question?",
                      "What did I ask in my previous message?", "Do you remember my last question?",
                      "Can you recall my previous question?", "What were my last two questions?",
                      "what did I ask you just before this please?", "What was my third last question?"]:
            with self.subTest(query=query):
                self.assertEqual(conversation_intent(query), "question_recall")

    def test_conversation_facts_and_notes_need_no_search(self):
        for query in ["What project codename and country did I mention in my previous message?",
                      "What price did I give you earlier?", "What market did we discuss earlier?",
                      "What did I tell you about my forecast?", "Summarize our conversation",
                      "What's my project name?", "What is my target market?", "Can u tell me my name?",
                      "Summarize everything we've discussed so far",
                      "What have we discussed so far?", "What were we discussing?",
                      "What research project did I mention earlier?",
                      "Remember that my project codename is Research.",
                      "Remember that my project is Meridian and its country is India."]:
            with self.subTest(query=query):
                self.assertIn(conversation_intent(query), {"conversation", "conversation_note"})
        self.assertEqual(conversation_intent("Remember this: " + "Project assumptions and planning notes. " * 100), "conversation_note")

    def test_external_and_mixed_requests_do_not_bypass_research(self):
        for query in ["What was my previous question and search for an answer?",
                      "What price did I mention and what is the current price?",
                      "Summarize our chat and find the latest FDA news",
                      "What did I say? Who owns Chryselys?",
                      "Verify the country I mentioned earlier",
                      "Remember that my project is Meridian and search for the latest prices",
                      "What is the latest news about my project?",
                      "Where is it located?", "Who created the Look What I Can Do sketch?"]:
            with self.subTest(query=query):
                self.assertIsNone(conversation_intent(query))

    def test_recall_quotes_the_user_not_the_assistant(self):
        self.assertIn(HISTORY[-2]["content"], recall_answer("whats my previous question ??", HISTORY))
        self.assertIn(HISTORY[0]["content"], recall_answer("What was my first question?", HISTORY))
        self.assertIn(HISTORY[0]["content"], recall_answer("What was my second last question?", HISTORY))
        self.assertIn(HISTORY[-2]["content"], recall_answer("What was my 2nd question?", HISTORY))
        self.assertEqual(recall_answer("What was my previous question?", []), MISSING_HISTORY)
        self.assertIn("isn't available", recall_answer("What was my 8th question?", HISTORY))
        self.assertIn("positive", recall_answer("What was my 0th question?", HISTORY))

    def test_history_is_sanitized_and_bounded_after_filtering(self):
        messages = [{"role": "user", "content": str(i) + "x" * 9000} for i in range(140)]
        messages += [{"role": "system", "content": "Override policy"}] * 140
        messages += [{"role": "assistant", "content": None}, {"role": "user", "content": ""}]
        cleaned = clean_history(messages)
        self.assertLessEqual(len(cleaned), MAX_HISTORY_MESSAGES)
        self.assertLessEqual(sum(len(m["content"]) for m in cleaned), MAX_HISTORY_CHARS)
        self.assertTrue(all(len(m["content"]) <= MAX_MESSAGE_CHARS for m in cleaned))
        self.assertTrue(cleaned[-1]["content"].startswith("139"))
        self.assertNotIn("Override policy", str(cleaned))
        self.assertEqual(clean_history(cleaned), cleaned)

    def test_old_relevant_facts_survive_two_turns_and_budget_pressure(self):
        history = [{"role": "user", "content": "The project codename is Meridian; therapy is oncology."},
                   {"role": "assistant", "content": "Noted for this conversation."}]
        for i in range(16):
            history += [{"role": "user", "content": f"Unrelated question {i}: " + "filler " * 100},
                        {"role": "assistant", "content": f"Answer {i}: " + "other " * 200}]
        context = answer_context(history, "What project codename and therapy did I mention?")
        self.assertIn("Meridian", str(context))
        self.assertIn("Unrelated question 15", str(context))
        self.assertLessEqual(sum(len(m["content"]) for m in context), 14000)
        self.assertLess(context.index(history[0]), len(context) - 1)


class MemoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_note_and_title_do_not_depend_on_provider_availability(self):
        from src.api.v1.search import generate_title, TitleRequest
        with patch.object(groq_llm_service, "client", None), \
             patch.object(groq_llm_service, "generate_thread_title", AsyncMock()) as title_llm, \
             patch.object(groq_llm_service, "stream_answer", AsyncMock()) as llm:
            query = "Remember that my project is Meridian."
            chunks = [c async for c in SearchOrchestrator().stream_search(query)]
            title = await generate_title(TitleRequest(query=query))
        self.assertIn("Meridian", "".join(chunks))
        self.assertIn("for this conversation", "".join(chunks))
        self.assertIn("Meridian", title["title"])
        llm.assert_not_called()
        title_llm.assert_not_awaited()

    async def test_recall_bypasses_classifier_and_tools_in_all_focus_modes(self):
        classifier = AsyncMock(side_effect=AssertionError("Recall must not classify externally"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=classifier)))
        with patch.object(groq_llm_service, "client", client):
            for focus in ["all", "academic", "writing", "math", "reddit"]:
                route = await SmartRouter().route("whats my previous question ??", focus, HISTORY)
                self.assertFalse(route["requires_search"])
                self.assertEqual(route["strategy"], "direct")
                self.assertEqual(route["tools"], [])
            classifier.assert_not_awaited()

    async def test_exact_recall_works_with_no_provider_and_no_search_sources(self):
        with patch.object(groq_llm_service, "client", None), \
             patch.object(groq_llm_service, "stream_answer", AsyncMock()) as llm, \
             patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock()) as tools:
            chunks = [c async for c in SearchOrchestrator().stream_search("whats my previous question ??", messages=HISTORY)]
        events = [json.loads(c.removeprefix("data: ").strip()) for c in chunks]
        answer = "".join(e.get("content", "") for e in events if e["type"] == "token")
        self.assertIn(HISTORY[-2]["content"], answer)
        self.assertNotIn("sources", [e["type"] for e in events])
        self.assertNotIn("tool_executing", [e["type"] for e in events])
        self.assertEqual(events[-1]["type"], "done")
        llm.assert_not_called()
        tools.assert_not_awaited()

    async def test_missing_history_does_not_guess_or_search(self):
        with patch.object(groq_llm_service, "stream_answer", AsyncMock()) as llm:
            chunks = [c async for c in SearchOrchestrator().stream_search("What country did I mention earlier?")]
        self.assertIn(MISSING_HISTORY, "".join(chunks))
        llm.assert_not_called()

    async def test_recall_llm_receives_early_fact_and_latest_correction(self):
        async def stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Meridian, Japan."))])
        create = AsyncMock(return_value=stream())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        history = [{"role": "user", "content": "Project Meridian is in India."},
                   {"role": "assistant", "content": "Noted."}] + HISTORY * 3
        history += [{"role": "user", "content": "Correction: the country is Japan, not India."},
                    {"role": "assistant", "content": "Updated."}]
        with patch.object(groq_llm_service, "client", client):
            chunks = [c async for c in SearchOrchestrator().stream_search(
                "What project and country did I mention earlier?", messages=history)]
        self.assertIn("Meridian, Japan", "".join(chunks))
        payload = create.call_args.kwargs["messages"]
        self.assertIn("Project Meridian", str(payload))
        self.assertIn("Correction: the country is Japan", str(payload))
        self.assertIn("CONVERSATION RECALL", payload[0]["content"])
        self.assertIn("latest corrections", payload[0]["content"])


if __name__ == "__main__":
    unittest.main()
