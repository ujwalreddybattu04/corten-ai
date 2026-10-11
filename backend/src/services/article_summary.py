"""Keep incomplete provider drafts out of published Discover summaries."""
import re

from src.services.llm_runtime import LLMProviderError


class ArticleSummaryIncompleteError(LLMProviderError):
    code = "article_summary_incomplete"

    def __init__(self):
        super().__init__("The summary could not be completed. Please retry or read the original article.")


def complete_summary(content: str | None, finish_reason: str | None) -> str | None:
    """Require a normal finish and sentence ending; never trim or fabricate an ending.

    320 words allows small variation around the 180–260 word target. Shorter
    summaries are valid when the available evidence does not support more detail.
    """
    text = (content or "").strip()
    if finish_reason != "stop" or not text or len(text.split()) > 320:
        return None
    # Ignore citation/Markdown suffixes only for this check; return the original
    # text verbatim so no facts, citations or closing sentences are discarded.
    ending = re.sub(r"\s*(?:[*_]*\[\d+(?:\s*,\s*\d+)*\][*_]*\s*)+$", "", text)
    ending = ending.rstrip(" \t\r\n*_\"'”’»)]")
    if not re.search(r"[.!?。！？]$", ending) or re.search(r"(?:\.\.\.|…)$", ending):
        return None
    return text
