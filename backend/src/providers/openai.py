"""OpenAI LLM provider implementation."""
from src.providers.base import BaseLLMProvider
from typing import AsyncGenerator

# TODO: Implement with openai library
class OpenAIProvider(BaseLLMProvider):
    async def generate(self, prompt: str, model: str = "gpt-4o", **kwargs) -> str:
        raise NotImplementedError

    async def stream(self, prompt: str, model: str = "gpt-4o", **kwargs) -> AsyncGenerator[str, None]:
        raise NotImplementedError
        yield  # type: ignore
