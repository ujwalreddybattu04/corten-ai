"""Google Gemini LLM provider implementation."""
from src.providers.base import BaseLLMProvider
from typing import AsyncGenerator

# TODO: Implement with google-generativeai library
class GoogleProvider(BaseLLMProvider):
    async def generate(self, prompt: str, model: str = "gemini-pro", **kwargs) -> str:
        raise NotImplementedError

    async def stream(self, prompt: str, model: str = "gemini-pro", **kwargs) -> AsyncGenerator[str, None]:
        raise NotImplementedError
        yield  # type: ignore
