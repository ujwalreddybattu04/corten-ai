"""Explicit provider selection, bounded retries and shared quota cooldowns.

Keep the chat.completions API used by routing, answers and reports. Providers are
never silently enabled just because a key is present. No raw provider error body
is returned to users or logged here.
"""
import asyncio
import math
import time
import httpx
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from groq import AsyncGroq
from openai import AsyncOpenAI


class LLMProviderError(RuntimeError):
    code = "llm_unavailable"
    retry_after_seconds = None


class LLMQuotaError(LLMProviderError):
    code = "llm_rate_limited"

    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = max(1, math.ceil(retry_after_seconds))
        seconds = self.retry_after_seconds
        wait = f"{seconds} seconds" if seconds < 60 else f"about {math.ceil(seconds / 60)} minutes"
        super().__init__(f"The AI provider's usage limit has been reached. Please try again in {wait}.")


def llm_error_details(exc: LLMProviderError) -> dict:
    details = {"message": str(exc), "code": exc.code}
    if exc.retry_after_seconds is not None:
        details["retry_after_seconds"] = exc.retry_after_seconds
    return details


def retry_delay(exc: Exception) -> float:
    """Honor Retry-After seconds or HTTP date; missing/invalid values wait a minute."""
    response = getattr(exc, "response", None)
    raw = getattr(response, "headers", {}).get("retry-after", "")
    try:
        seconds = float(raw)
        if math.isfinite(seconds) and seconds >= 0:
            return max(0.1, seconds)
    except (ValueError, TypeError):
        try:
            reset = parsedate_to_datetime(raw)
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=timezone.utc)
            return max(0.1, (reset - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return 60.0


@dataclass
class Endpoint:
    name: str
    client: object
    model: str = ""  # Groq keeps the per-task model supplied by the caller.


class ManagedStream:
    """Close SDK streams; never restart or mix answers after streaming starts."""
    def __init__(self, stream, runtime, quota_key):
        self._stream = stream
        self._iterator = stream.__aiter__()
        self._runtime = runtime
        self._quota_key = quota_key
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self._iterator.__anext__()
        except StopAsyncIteration:
            await self.close()
            raise
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception as exc:
            await self.close()
            if getattr(exc, "status_code", None) == 429:
                delay = self._runtime.block(self._quota_key, exc)
                raise LLMQuotaError(delay) from None
            raise LLMProviderError("The AI connection was interrupted. Please retry your request.") from None

    async def close(self):
        if not self._closed:
            self._closed = True
            closer = getattr(self._stream, "close", None) or getattr(self._stream, "aclose", None)
            if closer:
                await closer()


class LLMRuntime:
    def __init__(self, endpoints: list[Endpoint], max_output_tokens: int = 2048):
        self.endpoints = endpoints
        self.max_output_tokens = max_output_tokens
        self._blocked_until = {}
        self._disabled_credentials = set()
        self.chat = self
        self.completions = self

    def block(self, key, exc):
        delay = retry_delay(exc)
        self._blocked_until[key] = max(self._blocked_until.get(key, 0), time.monotonic() + delay)
        return delay

    def _options(self, endpoint, kwargs):
        options = dict(kwargs)
        options["model"] = endpoint.model or kwargs["model"]
        options["max_tokens"] = min(kwargs.get("max_tokens", self.max_output_tokens), self.max_output_tokens)
        if endpoint.name == "groq":
            if options["model"].startswith("openai/gpt-oss-"):
                options.setdefault("reasoning_effort", "low")
        else:
            options.pop("reasoning_effort", None)
            if endpoint.name == "gemini" and options["model"] == "gemini-2.5-flash":
                # Optional thinking would otherwise consume tiny JSON/title budgets.
                options["extra_body"] = {"extra_body": {"google": {"thinking_config": {"thinking_budget": 0}}}}
        return options

    async def create(self, **kwargs):
        quota_waits = []
        for index, endpoint in enumerate(self.endpoints):
            if index in self._disabled_credentials:
                continue
            options = self._options(endpoint, kwargs)
            # Two credentials for one provider must not share the application's
            # cooldown. The provider may still enforce a shared organization quota.
            key = (index, options["model"])
            for attempt in range(2):
                wait = self._blocked_until.get(key, 0) - time.monotonic()
                if wait > 0:
                    quota_waits.append(wait)
                    break
                try:
                    result = await endpoint.client.chat.completions.create(**options)
                    if kwargs.get("stream"):
                        return ManagedStream(result, self, key)
                    return result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    status = getattr(exc, "status_code", None)
                    if status == 429:
                        delay = self.block(key, exc)
                        # Prefer the explicitly configured fallback. Only retry a
                        # short wait once, without SDK retries multiplying attempts.
                        if attempt == 0 and index == len(self.endpoints) - 1 and delay <= 2:
                            # Event-loop timers can wake slightly before monotonic
                            # deadlines on Windows. A small margin avoids retrying
                            # early or abandoning the one allowed short retry.
                            await asyncio.sleep(delay + 0.05)
                            continue
                        quota_waits.append(delay)
                        break
                    if status in (400, 422):
                        raise LLMProviderError("The AI provider rejected this request. Try a shorter message or contact the administrator.") from None
                    if status in (401, 403):
                        # Revoked/invalid keys cannot recover without a configuration
                        # change. Skip them until the process reloads its credentials.
                        self._disabled_credentials.add(index)
                    break
        if quota_waits:
            raise LLMQuotaError(min(quota_waits)) from None
        raise LLMProviderError("The AI service is temporarily unavailable. Please try again or contact the administrator.") from None


def build_llm_client(settings):
    endpoints = []
    for provider in dict.fromkeys((settings.LLM_PROVIDER, settings.LLM_FALLBACK_PROVIDER)):
        if provider == "groq":
            keys = dict.fromkeys([settings.GROQ_API_KEY.strip(), *settings.GROQ_FALLBACK_API_KEYS])
            for key in keys:
                if key:
                    endpoints.append(Endpoint("groq", AsyncGroq(api_key=key, max_retries=0, timeout=httpx.Timeout(30, connect=5))))
        elif provider == "gemini" and settings.GOOGLE_AI_API_KEY:
            endpoints.append(Endpoint("gemini", AsyncOpenAI(
                api_key=settings.GOOGLE_AI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                max_retries=0, timeout=30,
            ), settings.GEMINI_MODEL))
    return LLMRuntime(endpoints, settings.LLM_MAX_OUTPUT_TOKENS) if endpoints else None
