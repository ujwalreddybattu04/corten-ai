"""Quota, provider failover and streaming regressions without external API calls."""
import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from groq import AsyncGroq
from openai import AsyncOpenAI

from src.config.settings import Settings
from src.services.llm_runtime import (
    Endpoint, LLMProviderError, LLMQuotaError, LLMRuntime, build_llm_client, retry_delay,
)


def completion():
    return {"id": "test", "object": "chat.completion", "created": 0, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]}


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()

    def client(self, handler, kind="groq"):
        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        cls = AsyncGroq if kind == "groq" else AsyncOpenAI
        client = cls(api_key="unit-test-key", max_retries=0, http_client=http_client)
        self.clients.append(client)
        return client

    async def test_long_quota_wait_blocks_answers_and_auxiliary_calls_without_retries(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(429, headers={"retry-after": "3600"},
                                  json={"error": {"message": "private provider error", "type": "tokens", "code": "rate_limit_exceeded"}})
        runtime = LLMRuntime([Endpoint("groq", self.client(handler))])
        for budget in (2048, 512, 1536):
            with self.assertRaises(LLMQuotaError) as result:
                await runtime.create(model="openai/gpt-oss-20b", messages=[], max_tokens=budget)
            self.assertGreaterEqual(result.exception.retry_after_seconds, 3599)
            self.assertNotIn("private provider error", str(result.exception))
        self.assertEqual(len(requests), 1)

    async def test_short_retry_after_is_retried_once(self):
        requests = []
        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(429, headers={"retry-after": "0.1"}, json={"error": {"message": "wait"}})
            return httpx.Response(200, json=completion())
        runtime = LLMRuntime([Endpoint("groq", self.client(handler))])
        response = await runtime.create(model="test", messages=[])
        self.assertEqual(response.choices[0].message.content, "OK")
        self.assertEqual(len(requests), 2)

    async def test_repeated_short_limit_stops_after_two_attempts(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(429, headers={"retry-after": "0.1"}, json={"error": {"message": "wait"}})
        runtime = LLMRuntime([Endpoint("groq", self.client(handler))])
        with self.assertRaises(LLMQuotaError):
            await runtime.create(model="test", messages=[])
        self.assertEqual(len(requests), 2)

    async def test_explicit_fallback_changes_model_and_keeps_context(self):
        primary_requests, secondary_requests = [], []
        def primary(request):
            primary_requests.append(request)
            return httpx.Response(429, headers={"retry-after": "600"}, json={"error": {"message": "wait"}})
        def secondary(request):
            secondary_requests.append(json.loads(request.content))
            return httpx.Response(200, json=completion())
        runtime = LLMRuntime([Endpoint("groq", self.client(primary)),
                              Endpoint("gemini", self.client(secondary, "gemini"), "gemini-2.5-flash")])
        messages = [{"role": "user", "content": "Keep the full conversation."}]
        for _ in range(2):
            await runtime.create(model="openai/gpt-oss-20b", messages=messages,
                                 max_tokens=512, reasoning_effort="low", response_format={"type": "json_object"})
        self.assertEqual(len(primary_requests), 1)
        self.assertEqual(len(secondary_requests), 2)
        self.assertEqual(secondary_requests[0]["model"], "gemini-2.5-flash")
        self.assertEqual(secondary_requests[0]["messages"], messages)
        self.assertNotIn("reasoning_effort", secondary_requests[0])
        self.assertEqual(secondary_requests[0]["extra_body"]["google"]["thinking_config"]["thinking_budget"], 0)

    async def test_three_groq_credentials_fail_over_and_skip_cooling_keys(self):
        calls = [0, 0, 0]
        def handler(index):
            def respond(request):
                calls[index] += 1
                if index < 2:
                    return httpx.Response(429, headers={"retry-after": "600"}, json={"error": {"message": "wait"}})
                return httpx.Response(200, json=completion())
            return respond
        runtime = LLMRuntime([Endpoint("groq", self.client(handler(index))) for index in range(3)])
        for _ in range(2):
            response = await runtime.create(model="openai/gpt-oss-20b", messages=[])
            self.assertEqual(response.choices[0].message.content, "OK")
        self.assertEqual(calls, [1, 1, 2])

    async def test_shared_quota_on_all_keys_stops_without_looping(self):
        calls = [0, 0, 0]
        def handler(index):
            def respond(request):
                calls[index] += 1
                return httpx.Response(429, headers={"retry-after": "3600"}, json={"error": {"message": "shared organization quota"}})
            return respond
        runtime = LLMRuntime([Endpoint("groq", self.client(handler(index))) for index in range(3)])
        for _ in range(2):
            with self.assertRaises(LLMQuotaError):
                await runtime.create(model="test", messages=[])
        self.assertEqual(calls, [1, 1, 1])

    async def test_invalid_credential_is_skipped_until_configuration_reload(self):
        calls = [0, 0]
        def invalid(request):
            calls[0] += 1
            return httpx.Response(401, json={"error": {"message": "revoked key"}})
        def valid(request):
            calls[1] += 1
            return httpx.Response(200, json=completion())
        runtime = LLMRuntime([Endpoint("groq", self.client(invalid)), Endpoint("groq", self.client(valid))])
        for _ in range(2):
            await runtime.create(model="test", messages=[])
        self.assertEqual(calls, [1, 2])

    async def test_output_limits_cover_deep_research_and_uncapped_requests(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=completion())
        runtime = LLMRuntime([Endpoint("groq", self.client(handler))], max_output_tokens=2048)
        await runtime.create(model="openai/gpt-oss-20b", messages=[], max_tokens=8192)
        await runtime.create(model="openai/gpt-oss-20b", messages=[])
        self.assertEqual([x["max_tokens"] for x in requests], [2048, 2048])
        self.assertEqual(requests[0]["reasoning_effort"], "low")

    async def test_invalid_request_is_not_retried_or_forwarded_to_fallback(self):
        def handler(request):
            return httpx.Response(400, json={"error": {"message": "private error detail"}})
        fallback = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())))
        runtime = LLMRuntime([Endpoint("groq", self.client(handler)), Endpoint("gemini", fallback, "gemini-2.5-flash")])
        with self.assertRaises(LLMProviderError) as result:
            await runtime.create(model="test", messages=[])
        self.assertNotIn("private error detail", str(result.exception))
        fallback.chat.completions.create.assert_not_awaited()

    async def test_cancellation_stops_during_retry(self):
        seen = asyncio.Event()
        def handler(request):
            seen.set()
            return httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"message": "wait"}})
        runtime = LLMRuntime([Endpoint("groq", self.client(handler))])
        task = asyncio.create_task(runtime.create(model="test", messages=[]))
        await seen.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_interrupted_stream_never_restarts_or_mixes_answers(self):
        async def chunks():
            yield "first chunk"
            raise RuntimeError("private connection failure")
        create = AsyncMock(return_value=chunks())
        primary = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        fallback = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())))
        runtime = LLMRuntime([Endpoint("groq", primary), Endpoint("gemini", fallback, "gemini-2.5-flash")])
        stream = await runtime.create(model="test", messages=[], stream=True)
        self.assertEqual(await anext(stream), "first chunk")
        with self.assertRaises(LLMProviderError) as result:
            await anext(stream)
        self.assertNotIn("private connection failure", str(result.exception))
        fallback.chat.completions.create.assert_not_awaited()
        create.assert_awaited_once()

    async def test_quota_is_reported_in_chat_sse_with_retry_time(self):
        from src.services.llm_service import groq_llm_service
        from src.services.search_orchestrator import SearchOrchestrator
        async def limited(*args, **kwargs):
            raise LLMQuotaError(3600)
            yield  # Keep this a streaming generator.
        route = {"strategy": "direct", "query_type": "creative", "requires_search": False}
        with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
             patch.object(groq_llm_service, "stream_answer", limited):
            chunks = [chunk async for chunk in SearchOrchestrator().stream_search("Write a short poem")]
        events = [json.loads(chunk.removeprefix("data: ")) for chunk in chunks]
        error = next(event for event in events if event["type"] == "error")
        self.assertEqual(error["code"], "llm_rate_limited")
        self.assertEqual(error["retry_after_seconds"], 3600)
        self.assertIn("60 minutes", error["message"])
        self.assertEqual(events[-1]["type"], "done")

    async def test_standard_search_prioritizes_answer_without_redundant_planning_call(self):
        from src.services.llm_service import groq_llm_service
        from src.services.search_orchestrator import SearchOrchestrator
        from src.tools import ToolResult
        order = []
        async def answer(*args, **kwargs):
            order.append("answer")
            yield "An answer based on evidence [1]."
        async def suggestions(*args):
            order.append("suggestions")
            return []
        source = {"url": "https://example.com/evidence", "title": "Evidence", "snippet": "Verified fixture evidence."}
        result = ToolResult(success=True, tool_name="web_search", data={"results": [source]}, sources=[source])
        route = {"strategy": "standard", "query_type": "factual", "requires_search": True,
                 "tools": ["web_search"], "reasoning": "Find fresh evidence"}
        with patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
             patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock(return_value=[result])), \
             patch("src.services.search_orchestrator.tool_executor.execute_single", AsyncMock(return_value=ToolResult(success=False))), \
             patch.object(groq_llm_service, "generate_research_plan", AsyncMock()) as planner, \
             patch.object(groq_llm_service, "stream_answer", answer), \
             patch.object(groq_llm_service, "generate_follow_up_questions", suggestions):
            chunks = [chunk async for chunk in SearchOrchestrator().stream_search("An ordinary research request")]
        planner.assert_not_awaited()
        self.assertEqual(order, ["answer", "suggestions"])
        self.assertIn("An answer based on evidence", "".join(chunks))


class ConfigurationTests(unittest.TestCase):
    def test_retry_after_http_date_and_invalid_values(self):
        date = format_datetime(datetime.now(timezone.utc) + timedelta(minutes=3), usegmt=True)
        for value, lower in [(date, 178), ("invalid", 60), ("nan", 60), ("-5", 60)]:
            exc = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": value}))
            self.assertGreaterEqual(retry_delay(exc), lower)

    def test_extra_keys_do_not_enable_an_unselected_provider(self):
        config = Settings(_env_file=None, GROQ_API_KEY="unit-test-key", GOOGLE_AI_API_KEY="unit-test-key")
        with patch("src.services.llm_runtime.AsyncGroq", return_value=object()), \
             patch("src.services.llm_runtime.AsyncOpenAI") as alternate:
            runtime = build_llm_client(config)
        self.assertEqual([x.name for x in runtime.endpoints], ["groq"])
        alternate.assert_not_called()

    def test_independent_hosted_provider_can_be_selected(self):
        config = Settings(_env_file=None, LLM_PROVIDER="gemini", GOOGLE_AI_API_KEY="unit-test-key")
        with patch("src.services.llm_runtime.AsyncGroq") as groq, \
             patch("src.services.llm_runtime.AsyncOpenAI", return_value=object()) as hosted:
            runtime = build_llm_client(config)
        groq.assert_not_called()
        self.assertEqual(runtime.endpoints[0].model, "gemini-2.5-flash")
        self.assertEqual(hosted.call_args.kwargs["base_url"], "https://generativelanguage.googleapis.com/v1beta/openai/")
        self.assertEqual(hosted.call_args.kwargs["max_retries"], 0)

    def test_groq_keys_are_deduplicated_and_all_unique_credentials_are_loaded(self):
        config = Settings(_env_file=None, GROQ_API_KEY="primary-test", GROQ_FALLBACK_API_KEYS=[
            " fallback-one ", "", "fallback-two", "primary-test", "fallback-one"][:4])
        with patch("src.services.llm_runtime.AsyncGroq", return_value=object()) as constructor:
            runtime = build_llm_client(config)
        self.assertEqual(len(runtime.endpoints), 3)
        self.assertEqual([x.kwargs["api_key"] for x in constructor.call_args_list],
                         ["primary-test", "fallback-one", "fallback-two"])


if __name__ == "__main__":
    unittest.main()
