"""Answer modes: which Groq model, reasoning effort and output budget answer a question.

Auto picks per question; users can choose Fast, Pro or Extended thinking explicitly.
Images always use the vision model, which is the only Groq model here that accepts them.
"""
from dataclasses import dataclass
from typing import Literal
from src.config.settings import settings

Mode = Literal["auto", "fast", "pro", "think"]
MODES = ("auto", "fast", "pro", "think")


@dataclass(frozen=True)
class AnswerProfile:
    mode: str
    model: str
    reasoning_effort: str | None
    max_tokens: int
    evidence_chars: int
    show_reasoning: bool = False

    @property
    def label(self) -> str:
        return {"fast": "Fast", "pro": "Pro", "think": "Extended thinking", "vision": "Vision"}[self.mode]


def fast() -> AnswerProfile:
    return AnswerProfile("fast", settings.DEFAULT_MODEL, "low", settings.LLM_MAX_OUTPUT_TOKENS, 12_000)


def pro() -> AnswerProfile:
    return AnswerProfile("pro", settings.HEAVY_MODEL, "medium", settings.LLM_HEAVY_MAX_OUTPUT_TOKENS, 48_000)


def think() -> AnswerProfile:
    return AnswerProfile("think", settings.HEAVY_MODEL, "high", settings.LLM_HEAVY_MAX_OUTPUT_TOKENS, 48_000, show_reasoning=True)


def vision() -> AnswerProfile:
    return AnswerProfile("vision", settings.VISION_MODEL, None, settings.LLM_HEAVY_MAX_OUTPUT_TOKENS, 32_000)


def resolve(requested: str | None, *, complexity: int = 3, strategy: str = "standard",
            has_images: bool = False, needs_long_output: bool = False, long_context: bool = False) -> AnswerProfile:
    """Choose the profile for one answer. Explicit choices win except where a model cannot do the job."""
    if has_images:
        return vision()
    requested = requested if requested in MODES else "auto"
    if requested == "fast":
        # Fast cannot hold very long documents or produce long artifacts reliably.
        return pro() if (needs_long_output or long_context) else fast()
    if requested == "pro":
        return pro()
    if requested == "think":
        return think()
    if strategy == "deep" or complexity >= 4 or needs_long_output or long_context:
        return pro()
    return fast()
