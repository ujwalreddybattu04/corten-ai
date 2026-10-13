"""A LangChain chat model over Corten's own LLM runtime.

Agents use LangChain and LangGraph, but every model call still goes through `LLMRuntime`, which owns quota
cooldowns, failover across configured keys and per-model output limits. Using the provider SDK through
langchain-groq would bypass all of that and pin an older SDK.
"""
import asyncio
from typing import Any, AsyncIterator, Sequence

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, convert_to_openai_messages
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.services.llm_runtime import LLMProviderError, LLMQuotaError

MAX_QUOTA_WAIT = 25   # per-minute token windows reset within this; longer waits fail fast with the provider's message


class CortenChatModel(BaseChatModel):
    runtime: Any                     # LLMRuntime (chat.completions.create compatible)
    model: str
    fallback_model: str | None = None   # used when `model` is out of quota; each model has its own provider limit
    max_tokens: int = 4096
    temperature: float = 0.2
    reasoning_effort: str = "low"

    @property
    def _llm_type(self) -> str:
        return "corten-runtime"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model, "reasoning_effort": self.reasoning_effort}

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None, **kwargs: Any):
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        if tool_choice in ("any", "required"):
            kwargs["tool_choice"] = "required"
        elif tool_choice in ("auto", "none"):
            kwargs["tool_choice"] = tool_choice
        return self.bind(tools=formatted, **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("Corten agents run asynchronously.")

    def _payload(self, messages: list[BaseMessage], stop: list[str] | None, kwargs: dict) -> dict:
        payload = {"model": self.model, "messages": convert_to_openai_messages(messages), "stream": True,
                   "temperature": self.temperature, "max_tokens": self.max_tokens}
        if self.model.startswith("openai/gpt-oss-"):
            payload["reasoning_effort"] = self.reasoning_effort
        if kwargs.get("tools"):
            payload["tools"] = kwargs["tools"]
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        if stop:
            payload["stop"] = stop
        return payload

    async def _astream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                       run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        payload = self._payload(messages, stop, kwargs)
        model, attempts = self.model, 0
        while True:
            attempts += 1
            emitted = False
            try:
                async for generation in self._stream_once({**payload, "model": model}, run_manager):
                    emitted = True
                    yield generation
                return
            except LLMQuotaError as error:
                # Never retry once output began. The other model has its own quota, so switch first; then a short
                # provider cooldown is worth waiting for once, because the agent has already done work for this answer.
                if emitted or attempts >= 3:
                    raise
                if self.fallback_model and model != self.fallback_model:
                    model = self.fallback_model
                    continue
                if (error.retry_after_seconds or 99) > MAX_QUOTA_WAIT:
                    raise
                await asyncio.sleep((error.retry_after_seconds or 1) + 0.3)
                model = self.model
            except LLMProviderError:
                # A dropped stream or a rejected tool call often succeeds on a second try; never after output began.
                if emitted or attempts >= 2:
                    raise
                await asyncio.sleep(1.0)

    async def _stream_once(self, payload: dict, run_manager) -> AsyncIterator[ChatGenerationChunk]:
        stream = await self.runtime.create(**payload)
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = choices[0].delta
            text = getattr(delta, "content", None) or ""
            calls = [tool_call_chunk(name=getattr(call.function, "name", None), args=getattr(call.function, "arguments", None),
                                     id=getattr(call, "id", None), index=getattr(call, "index", 0))
                     for call in (getattr(delta, "tool_calls", None) or [])]
            finish = choices[0].finish_reason
            if not text and not calls and not finish:
                continue
            message = AIMessageChunk(content=text, tool_call_chunks=calls,
                                     response_metadata={"finish_reason": finish, "model_name": self.model} if finish else {})
            generation = ChatGenerationChunk(message=message)
            if text and run_manager:
                await run_manager.on_llm_new_token(text, chunk=generation)
            yield generation

    async def _agenerate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                         run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        merged: AIMessageChunk | None = None
        async for generation in self._astream(messages, stop, run_manager, **kwargs):
            merged = generation.message if merged is None else merged + generation.message
        if merged is None:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
        message = AIMessage(content=merged.content, tool_calls=merged.tool_calls,
                            invalid_tool_calls=merged.invalid_tool_calls, response_metadata=merged.response_metadata)
        return ChatResult(generations=[ChatGeneration(message=message)])
