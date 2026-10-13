"""How answers read: one answer style everywhere, exact dates for relative phrases, and no blank answers."""
import json
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.config import prompts
from src.services import space_service
from src.services.agents import research_agent, space_agent
from src.services.llm_service import groq_llm_service

TUESDAY = date(2026, 10, 13)


def dates(text, today=TUESDAY):
    return prompts.resolve_relative_dates(text, today)


def test_relative_dates_are_worked_out_in_code():
    # Live: "leave this Friday" asked on Tuesday 13 October 2026 was answered with "Friday, 20 October 2026".
    assert "'this Friday' is Friday 16 October 2026" in dates("Email my manager for leave this Friday")
    assert "'tomorrow' is Wednesday 14 October 2026" in dates("What is the weather tomorrow?")
    after = dates("Book it for the day after tomorrow")
    assert "'day after tomorrow' is Thursday 15 October 2026" in after and "'tomorrow' is" not in after
    assert "'last Friday' is Friday 9 October 2026" in dates("What did the FDA approve last Friday?")
    assert "'Monday' is Monday 19 October 2026" in dates("Schedule the call on Monday")
    ambiguous = dates("Can we meet next Friday?")
    assert "ambiguous" in ambiguous and "Friday 16 October 2026" in ambiguous and "Friday 23 October 2026" in ambiguous
    assert "'this month' is October 2026" in dates("FDA approvals this month")
    assert "'next month' is November 2026" in dates("launches next month")
    assert "'last month' is September 2026" in dates("sales last month")
    assert "'last year' is 2025" in dates("revenue last year")
    assert dates("What is GLP-1?") == ""
    # Said on a Friday, "this Friday" is today and "coming Friday" is next week's.
    friday = date(2026, 10, 16)
    assert "'this Friday' is Friday 16 October 2026" in dates("leave this Friday", friday)
    assert "'coming Friday' is Friday 23 October 2026" in dates("the coming Friday", friday)
    # Month and year boundaries.
    assert "'next month' is January 2027" in dates("next month", date(2026, 12, 31))
    assert "'last month' is December 2026" in dates("last month", date(2027, 1, 1))


def test_writing_requests_get_the_text_itself_and_questions_get_the_answer_first():
    for request in ("Write a short email to my manager asking for leave this Friday", "draft a LinkedIn post about our launch",
                    "Can you compose a thank-you letter for my team?", "rewrite this message to sound polite"):
        assert "Write the requested text directly" in prompts.style_reminder(query=request), request
    for question in ("What is GLP-1?", "How do interest rates affect inflation?", "Who wrote this letter of the law?"):
        reminder = prompts.style_reminder(cited=True, query=question)
        assert "first one or two plain sentences" in reminder and "right after the claim" in reminder, question
    assert "right after the claim" not in prompts.style_reminder(query="What is GLP-1?")


def test_todays_date_carries_its_weekday_and_the_coming_week():
    context = prompts.date_context(TUESDAY)
    assert context.startswith("Tuesday, 13 October 2026") and "Friday 16 October" in context and "Tuesday 20 October" in context


def test_every_answer_path_uses_the_shared_answer_style():
    values = {"brand_name": "Corten", "company_name": "Chryselys", "current_date": prompts.date_context(TUESDAY)}
    for template in (prompts.RAG_SYSTEM_PROMPT, prompts.DIRECT_SYSTEM_PROMPT, research_agent.DEEP_SYNTHESIS_PROMPT):
        text = template.format(**values)          # no stray braces anywhere in the style text
        assert "ANSWER STYLE" in text and "never 10/12/2026" in text and "Tuesday, 13 October 2026" in text
    space = space_service.SpaceContext(space_id=uuid4(), name="Numbers", template="tpl_data")
    prompt = space_agent.system_prompt(space, "", "")
    assert "ANSWER STYLE" in prompt and "the next seven days" in prompt
    # The old rules that forced headings and tables onto every answer are gone.
    assert "Level 2 Headers" not in prompts.RAG_SYSTEM_PROMPT and "MUST use Markdown tables for all" not in prompts.RAG_SYSTEM_PROMPT
    # The format example bolds a figure, not a sentence, because models copy examples.
    assert "**USD 4.1 billion**" in prompts.RAG_SYSTEM_PROMPT


class FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = self.completions = self       # like LLMRuntime: client.chat.completions.create

    async def create(self, **options):
        self.calls.append(options)

        async def stream():
            yield NS(choices=[NS(delta=NS(content="Done.", reasoning=None))])
        return stream()


@pytest.mark.asyncio
async def test_the_model_receives_exact_dates_with_the_question():
    fake = FakeClient()
    with patch.object(groq_llm_service, "client", fake):
        [chunk async for chunk in groq_llm_service.stream_answer("Write an email asking for leave this Friday", [])]
    request = fake.calls[0]["messages"][-1]["content"]
    assert "(Dates for reference, from today" in request and "'this Friday' is Friday" in request
    assert "the next seven days" in fake.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_an_exhausted_answer_model_hands_over_to_the_other_model():
    from src.config.settings import settings
    from src.services import answer_modes
    from src.services.llm_runtime import LLMQuotaError

    class Exhausted(FakeClient):
        async def create(self, **options):
            if options["model"] == settings.DEFAULT_MODEL:
                self.calls.append(options)
                raise LLMQuotaError(30)
            return await super().create(**options)
    fake = Exhausted()
    with patch.object(groq_llm_service, "client", fake):
        answer = "".join([c async for c in groq_llm_service.stream_answer("What is GLP-1?", [], profile=answer_modes.fast())])
    assert answer == "Done." and [c["model"] for c in fake.calls] == [settings.DEFAULT_MODEL, settings.HEAVY_MODEL]
    # Image questions need the vision model: no hand-over, the provider's limit is reported.
    fake = Exhausted()
    with patch.object(groq_llm_service, "client", fake), pytest.raises(LLMQuotaError):
        [c async for c in groq_llm_service.stream_answer("What is this?", [], profile=answer_modes.fast(), images=["data:image/png;base64,AA"])]


@pytest.mark.asyncio
async def test_deep_research_never_shows_a_blank_answer():
    agent = research_agent.ResearchAgent()
    found = {"results": [{"title": "Trial results", "url": "https://example.org/a", "snippet": "Evidence text."}]}

    async def blank(*_args, **_kwargs):
        yield ""
    with patch("src.services.web_search_service.tavily_search_service.search", AsyncMock(return_value=found)), \
         patch("src.services.serper_image_service.serper_image_service.search_images", AsyncMock(return_value=[])), \
         patch.object(agent, "_evaluate_gaps", AsyncMock(return_value={"sufficient": True})), \
         patch.object(agent, "_stream_synthesis", side_effect=lambda *a, **k: blank()) as synthesis:
        events = [json.loads(e[6:]) async for e in agent.run("Compare two drugs", ["drug A", "drug B"])]
    assert synthesis.call_count == 2                       # one retry
    assert not any(e["type"] == "token" and not e.get("content", "").strip() for e in events)
    assert [e["message"] for e in events if e["type"] == "error"] == ["The answer could not be written this time. Please try again."]
