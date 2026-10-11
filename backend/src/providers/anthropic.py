"""Anthropic LLM provider implementation."""
from src.providers.base import BaseLLMProvider
from typing import AsyncGenerator

# TODO: Implement with anthropic library
class AnthropicProvider(BaseLLMProvider):
    async def generate(self, prompt: str, model: str = "claude-3.5-sonnet", **kwargs) -> str:
        raise NotImplementedError

    async def stream(self, prompt: str, model: str = "claude-3.5-sonnet", **kwargs) -> AsyncGenerator[str, None]:
        raise NotImplementedError
        yield  # type: ignore
