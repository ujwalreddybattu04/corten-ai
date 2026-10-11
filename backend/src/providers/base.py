"""Abstract LLM provider interface."""
from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseLLMProvider(ABC):
    """Base class for all LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, model: str, **kwargs) -> str:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def stream(self, prompt: str, model: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response tokens."""
        ...
