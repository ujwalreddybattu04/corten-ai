"""Space agents: templates, data sources, tools, charts, the model adapter and the agent loop.

No network and no live model: data sources are fed recorded-shape responses, and the agent runs on Corten's real
LangChain adapter over a scripted provider, so tool calling, streaming and limits are exercised end to end.
"""
import asyncio
import json
import re
from datetime import date, timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from src.config.settings import settings
from src.services import file_builder, space_service
from src.services.agents import charts, data_sources, space_agent, space_templates, toolkit
from src.services.agents.chat_model import CortenChatModel
from src.services.agents.data_sources import DataSourceError
from src.services.chat_context import TurnContext
from src.services.llm_runtime import LLMProviderError, LLMQuotaError
from src.services.llm_service import groq_llm_service
from src.services.search_orchestrator import SearchOrchestrator
from src.tools import ToolResult
from test_spaces import OWNER, api, factory  # noqa: F401  (fixtures)

TODAY = date.today()
YEAR = TODAY.year


# ── A scripted provider behind the real adapter ───────────────────────────────────────────────────

def chunk(content=None, calls=None, finish=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=calls), finish_reason=finish)])


def text(*parts):
    return [chunk(part) for part in parts] + [chunk(finish="stop")]


def tool(name, args, call_id="call_1", preamble=None):
    call = NS(id=call_id, index=0, function=NS(name=name, arguments=json.dumps(args)))
    return ([chunk(preamble)] if preamble else []) + [chunk(calls=[call]), chunk(finish="tool_calls")]


class Stream:
    def __init__(self, chunks, error=None):
        self.chunks, self.error = chunks, error

    def __aiter__(self):
        return self._items()

    async def _items(self):
        for item in self.chunks:
            yield item
        if self.error:
            raise self.error


class FakeRuntime:
    """chat.completions.create with scripted replies: a list of chunks, (chunks, error) to fail mid-stream, or an
    exception to fail before any output. Every request payload is recorded."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    async def create(self, **payload):
        self.calls.append(payload)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return Stream(*reply) if isinstance(reply, tuple) else Stream(reply)


def tool_names(payload):
    return [item["function"]["name"] for item in payload.get("tools", [])]


async def run_agent(query, space, runtime, *, mode="auto", messages=None, raw=False, **options):
    model = CortenChatModel(runtime=runtime, model="openai/gpt-oss-120b", fallback_model="openai/gpt-oss-20b")
    with patch.object(space_agent, "agent_model", lambda _mode: model):
        events = [event async for event in space_agent.run_space_agent(query, messages or [], space, TurnContext(mode=mode), **options)]
    # SSE comments (keepalives) carry no event.
    return events if raw else [json.loads(event[6:]) for event in events if event.startswith("data: ")]


def answer_text(events):
    return "".join(e["content"] for e in events if e["type"] == "token")


def steps(events):
    return [(e["tool"], e["status"]) for e in events if e["type"] == "agent_step"]


def data_space(**fields):
    return space_service.SpaceContext(space_id=uuid4(), name="Numbers", template="tpl_data", **fields)


POINTS = [("2026-04-13", 250.0), ("2026-07-01", 300.0), ("2026-09-25", 341.07), ("2026-10-12", 340.97)]


def stock(symbol="AAPL", name="Apple Inc.", points=POINTS, currency="USD"):
    return {"symbol": symbol, "name": name, "currency": currency, "exchange": "NasdaqGS", "interval": "1d", "period": "6m",
            "points": points, "provider": "Yahoo Finance", "summary": data_sources.summarize_series(points),
            "source": data_sources._source(f"{name} ({symbol}) price history", f"https://finance.yahoo.com/quote/{symbol}/history")}


# ── The agent loop ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_chart_request_fetches_real_prices_and_draws_a_chart_instead_of_writing_code():
    # Live: "i need a graph of apple stocks" in a Data Analyst Space was answered with a Python script.
    runtime = FakeRuntime(
        tool("stock_prices", {"ticker": "aapl", "period": "6m"}, preamble="Let me fetch Apple's prices first."),
        tool("create_chart", {"dataset_ids": ["d1"], "title": "Apple (AAPL) share price"}, call_id="call_2"),
        text("Apple closed at $340.97 on 12 Oct 2026 【1†source】", ", up 36.39% over six months [1]."))
    with patch.object(data_sources, "stock_history", AsyncMock(return_value=stock())) as history:
        events = await run_agent("i need a graph of apple stocks", data_space(), runtime)
    history.assert_awaited_once_with("aapl", "6m")         # the data source normalizes tickers itself
    assert next(e["label"] for e in events if e["type"] == "agent_step") == "Fetching AAPL prices (6m)"
    assert steps(events) == [("stock_prices", "running"), ("stock_prices", "done"), ("create_chart", "running"), ("create_chart", "done")]
    answer = answer_text(events)
    # The chart comes first, drawn from the fetched series; the plan before the tool call is never shown.
    assert answer.count(':::artifact{type="react"') == 1 and answer.index(":::artifact") < answer.index("Apple closed")
    prose = answer.split("\n:::", 1)[1]
    assert "Let me fetch" not in answer and "import " not in prose and "```" not in prose
    # Citations are normalized and point at the price source.
    assert "【" not in answer and "2026 [1], up" in answer
    sources = [e for e in events if e["type"] == "sources"][-1]["sources"]
    assert [(s["citationIndex"], s["domain"]) for s in sources] == [(1, "finance.yahoo.com")]
    meta = [e for e in events if e["type"] == "meta"][0]
    assert meta["mode"] == "Data Analyst agent" and meta["tools_used"] == ["create_chart", "stock_prices"]
    # The model was equipped by the template, told the date, and saw the dataset id it charted.
    first = runtime.calls[0]
    assert {"stock_prices", "exchange_rates", "economic_data", "create_chart"} <= set(tool_names(first))
    assert "clinical_trials" not in tool_names(first) and first["tool_choice"] == "auto"
    assert "the Data Analyst agent" in first["messages"][0]["content"] and "Template: Data Analyst" in first["messages"][0]["content"]
    assert f"this year\" means {YEAR}" in first["messages"][-1]["content"]
    assert "Dataset d1" in runtime.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_when_the_research_budget_is_spent_the_agent_must_answer_and_fetched_data_is_charted():
    tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "META"]
    runtime = FakeRuntime(*[tool("stock_prices", {"ticker": t}, call_id=f"call_{i}") for i, t in enumerate(tickers)],
                          text("Here is how the five compare [1]."))
    with patch.object(data_sources, "stock_history", AsyncMock(side_effect=lambda t, p: stock(symbol=t, name=t))):
        events = await run_agent("compare big tech stocks", data_space(), runtime)
    assert len(runtime.calls) == space_agent.MAX_MODEL_CALLS
    final = runtime.calls[-1]
    assert final["tool_choice"] == "none" and "research budget is used up" in final["messages"][-1]["content"]
    assert "A chart is already shown" in final["messages"][-1]["content"]
    answer = answer_text(events)
    assert answer.count(":::artifact") == 1 and answer.rstrip().endswith("Here is how the five compare [1].")
    assert steps(events)[-2:] == [("create_chart", "running"), ("create_chart", "done")]


@pytest.mark.asyncio
async def test_identical_tool_calls_are_answered_from_memory():
    runtime = FakeRuntime(tool("stock_prices", {"ticker": "AAPL"}), tool("stock_prices", {"ticker": "aapl "}, call_id="call_2"),
                          text("Done."))
    with patch.object(data_sources, "stock_history", AsyncMock(return_value=stock())) as history:
        events = await run_agent("apple?", data_space(), runtime)
    history.assert_awaited_once()
    assert "You already called this" in runtime.calls[2]["messages"][-1]["content"]
    # Fetched prices are charted even though the model did not draw a chart, and the chart comes first.
    assert steps(events) == [("stock_prices", "running"), ("stock_prices", "done"),
                             ("create_chart", "running"), ("create_chart", "done")]
    answer = answer_text(events)
    assert answer.count(":::artifact") == 1 and answer.index(":::artifact") < answer.index("Done.")


@pytest.mark.asyncio
async def test_a_failing_tool_is_reported_to_the_model_and_the_user():
    runtime = FakeRuntime(tool("stock_prices", {"ticker": "ZZZZ"}), text("I could not find prices for ZZZZ."))
    with patch.object(data_sources, "stock_history", AsyncMock(side_effect=DataSourceError("No price data found for ZZZZ."))):
        events = await run_agent("graph ZZZZ", data_space(), runtime)
    failed = [e for e in events if e["type"] == "agent_step" and e["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["detail"] == "No price data found for ZZZZ."
    assert "could not answer: No price data found for ZZZZ." in runtime.calls[1]["messages"][-1]["content"]
    assert answer_text(events) == "I could not find prices for ZZZZ."


@pytest.mark.asyncio
async def test_an_exhausted_model_falls_back_to_the_other_model_before_failing():
    runtime = FakeRuntime(LLMQuotaError(90), text("Answer."))
    events = await run_agent("What is the euro worth?", data_space(), runtime)
    assert [call["model"] for call in runtime.calls] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert answer_text(events) == "Answer."
    # Both exhausted with a long wait: one clear error, no invented fallback text.
    events = await run_agent("What is the euro worth?", data_space(), FakeRuntime(LLMQuotaError(90), LLMQuotaError(90)))
    assert [e["type"] for e in events].count("error") == 1 and "usage limit" in next(e for e in events if e["type"] == "error")["message"]
    assert answer_text(events) == "" and events[-1]["type"] == "meta"


@pytest.mark.asyncio
async def test_a_stream_that_breaks_after_output_is_never_retried_or_mixed():
    runtime = FakeRuntime(([chunk("Partial answer about the euro that is long enough to be streamed to the reader. " * 3)],
                           LLMProviderError("The AI connection was interrupted. Please retry your request.")), text("Other."))
    events = await run_agent("euro?", data_space(), runtime)
    assert len(runtime.calls) == 1 and "Other." not in answer_text(events)
    assert any(e["type"] == "error" and "interrupted" in e["message"] for e in events)


@pytest.mark.asyncio
async def test_a_short_quota_wait_is_retried_once_on_the_same_model_without_a_fallback(monkeypatch):
    slept = []
    monkeypatch.setattr("src.services.agents.chat_model.asyncio.sleep", AsyncMock(side_effect=lambda s: slept.append(s)))
    runtime = FakeRuntime(LLMQuotaError(3), text("Answer."))
    model = CortenChatModel(runtime=runtime, model="openai/gpt-oss-20b")
    message = await model.ainvoke("hi")
    assert message.content == "Answer." and slept == [3.3] and [c["model"] for c in runtime.calls] == ["openai/gpt-oss-20b"] * 2


def test_fullwidth_citations_are_rewritten_across_stream_chunks():
    style = space_agent.CitationStyle()
    out = [style.feed("Rates rose 【"), style.feed("2†source】 and fell 【3, 4】"), style.feed(". Done【"), style.flush()]
    assert "".join(out) == "Rates rose [2] and fell [3][4]. Done【"
    # Text after an unclosed bracket is held only briefly: a newline or a long run releases it unchanged.
    assert space_agent.CitationStyle().feed("a 【b\nc") == "a 【b\nc"


def test_the_grounding_reminder_names_today_and_the_current_year():
    # The reminder uses the UTC date (the server's clock), which differs from a local date for part of the day.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    reminder = space_agent.grounding_reminder()
    assert today.isoformat() in reminder and f"means {today.year}" in reminder


# ── When the agent answers, and when the standard pipeline does ───────────────────────────────────

WEB_ROUTE = {"strategy": "quick", "query_type": "factual", "tools": ["web_search"], "requires_search": True}


async def answer_in(query, space, route=WEB_ROUTE, turn=None):
    called = []

    async def agent(question, messages, space, turn, **options):
        called.append((question, options))
        yield 'data: {"type": "token", "content": "Agent answer."}\n\n'

    async def classic(question, results, history, focus="all", **options):
        yield "Classic answer."

    with patch("src.services.agents.space_agent.run_space_agent", agent), \
         patch("src.services.search_orchestrator.smart_router.route", AsyncMock(return_value=route)), \
         patch("src.services.search_orchestrator.tool_executor.execute_tools", AsyncMock(return_value=[])), \
         patch("src.services.search_orchestrator.tool_executor.execute_single", AsyncMock(return_value=ToolResult(success=False))), \
         patch.object(groq_llm_service, "stream_answer", classic), \
         patch.object(groq_llm_service, "generate_follow_up_questions", AsyncMock(return_value=[])):
        events = [json.loads(e[6:]) for e in [e async for e in SearchOrchestrator().stream_search(query, "all", [], space=space, turn=turn)]]
    return called, answer_text(events), events


@pytest.mark.asyncio
async def test_space_questions_go_to_the_agent_except_where_the_standard_pipeline_is_better(monkeypatch):
    monkeypatch.setattr(settings, "SPACE_AGENTS_ENABLED", True)
    called, answer, events = await answer_in("i need a graph of apple stocks", data_space())
    assert [q for q, _ in called] == ["i need a graph of apple stocks"] and answer == "Agent answer." and events[-1]["type"] == "done"
    assert called[0][1] == {"attachments": None, "wants_artifact": False}
    request = "Export Apple's share price history as a CSV file"
    assert file_builder.detect(request)
    greeting = {"strategy": "direct", "query_type": "greeting", "tools": [], "requires_search": False}
    for query, space, route, turn in [
        ("Revenue?", data_space(web_search=False, has_files=True), WEB_ROUTE, None),      # files only: file pipeline
        ("hello", data_space(), greeting, None),                                           # Corten's own intents
        ("whats this about ??", data_space(), WEB_ROUTE, None),                            # the Space itself
        ("What is in this chart?", data_space(), WEB_ROUTE, TurnContext(images=["data:image/png;base64,AAAA"])),
        (request, data_space(), WEB_ROUTE, None),                                          # a downloadable file
    ]:
        if space.has_files:
            space.retrieve = AsyncMock(return_value=[])
        called, _, _ = await answer_in(query, space, route, turn)
        assert called == [], query
    # The kill switch returns every Space to the standard pipeline.
    monkeypatch.setattr(settings, "SPACE_AGENTS_ENABLED", False)
    called, answer, _ = await answer_in("i need a graph of apple stocks", data_space())
    assert called == [] and answer and answer != "Agent answer."


# ── Data sources (recorded response shapes, no network) ───────────────────────────────────────────

def fetch_by_url(routes):
    """A _fetch stand-in answering by URL substring; a route value that is an exception is raised."""
    seen = []

    async def fetch(url, params=None, **options):
        seen.append((url, params))
        for fragment, value in routes.items():
            if fragment in url:
                if isinstance(value, BaseException):
                    raise value
                return value
        raise AssertionError(f"unexpected request {url}")
    fetch.seen = seen
    return fetch


@pytest.mark.asyncio
async def test_stock_prices_are_parsed_per_trading_day_with_a_keyless_fallback(monkeypatch):
    yahoo = {"chart": {"result": [{"meta": {"gmtoffset": -14400, "currency": "USD", "longName": "Apple Inc.", "fullExchangeName": "NasdaqGS"},
                                   "timestamp": [1760362200, 1760448600, 1760535000, 1760538600],
                                   "indicators": {"quote": [{"close": [247.66, None, 249.34, 250.0]}]}}]}}
    monkeypatch.setattr(data_sources, "_fetch", fetch_by_url({"finance.yahoo.com": yahoo}))
    data = await data_sources.stock_history(" aapl ", "6m")
    # Missing closes are skipped and a repeated session date keeps its latest close.
    assert data["points"] == [("2025-10-13", 247.66), ("2025-10-15", 250.0)] and data["provider"] == "Yahoo Finance"
    assert data["summary"]["change_pct"] == round((250.0 - 247.66) / 247.66 * 100, 2)
    recent = [(TODAY - timedelta(days=days)).isoformat() for days in (9, 2)]
    csv = f"Date,Open,High,Low,Close,Volume\n2000-01-03,1,1,1,1,1\n{recent[0]},1,1,1,230.5,9\n{recent[1]},1,1,1,233.25,9\n"
    monkeypatch.setattr(data_sources, "_fetch", fetch_by_url({
        "finance.yahoo.com": DataSourceError("query1.finance.yahoo.com could not be reached. Try again shortly."), "stooq.com": csv}))
    data = await data_sources.stock_history("AAPL", "1m")
    assert data["provider"] == "Stooq" and data["points"] == [(recent[0], 230.5), (recent[1], 233.25)]
    for bad in ("", "AAPL; DROP", "a" * 30):
        with pytest.raises(DataSourceError):
            await data_sources.stock_history(bad)


@pytest.mark.asyncio
async def test_economic_data_comes_from_the_imf_with_projections_and_falls_back_to_the_world_bank(monkeypatch):
    imf = {"values": {"NGDP_RPCH": {"DEU": {"2014": 2.2, "2015": 1.5, str(YEAR): 1.3, str(YEAR + 1): 1.1},
                                    "FRA": {"2015": 1.1, str(YEAR): 0.4}, "ITA": {"2015": 0.8}}}}
    countries = {"countries": {"DEU": {"label": "Germany"}, "FRA": {"label": "France"}}}
    fetch = fetch_by_url({"datamapper/api/v1/countries": countries, "datamapper/api/v1/NGDP_RPCH": imf})
    monkeypatch.setattr(data_sources, "_fetch", fetch)
    data = await data_sources.economic_indicator(["de", "FRA"], "gdp_growth", 2015, YEAR)
    assert data["provider"] == "IMF" and data["projections_from"] == YEAR
    assert data["series"] == {"Germany": [("2015", 1.5), (str(YEAR), 1.3)], "France": [("2015", 1.1), (str(YEAR), 0.4)]}
    wb_rows = [{}, [{"country": {"value": "Germany"}, "date": "2016", "value": 2.23}, {"country": {"value": "Germany"}, "date": "2015", "value": 1.49},
                    {"country": {"value": "Germany"}, "date": "2017", "value": None}]]
    fetch = fetch_by_url({"imf.org": DataSourceError("www.imf.org could not be reached. Try again shortly."), "worldbank.org": wb_rows})
    monkeypatch.setattr(data_sources, "_fetch", fetch)
    data = await data_sources.economic_indicator(["DEU"], "gdp_growth", 2015, YEAR + 3)
    assert data["provider"] == "World Bank" and data["projections_from"] is None
    assert data["series"] == {"Germany": [("2015", 1.4900), ("2016", 2.23)]}
    assert fetch.seen[-1][1]["date"] == f"2015:{YEAR}"        # the World Bank only has past years
    # Indicators the IMF does not publish go straight to the World Bank.
    fetch = fetch_by_url({"worldbank.org": wb_rows})
    monkeypatch.setattr(data_sources, "_fetch", fetch)
    await data_sources.economic_indicator(["DE"], "life_expectancy", 2015, 2020)
    assert all("imf.org" not in url for url, _ in fetch.seen)
    for countries_, indicator in ((["Atlantis"], "gdp_growth"), ([], "gdp_growth"), (["DE"], "happiness")):
        with pytest.raises(DataSourceError):
            await data_sources.economic_indicator(countries_, indicator, 2015, 2020)


@pytest.mark.asyncio
async def test_trial_searches_filter_by_sponsor_phase_and_start_dates(monkeypatch):
    study = {"protocolSection": {"identificationModule": {"nctId": "NCT07830732", "briefTitle": "Mim8 in acquired haemophilia A"},
                                 "statusModule": {"overallStatus": "NOT_YET_RECRUITING", "startDateStruct": {"date": "2026-10-09"}},
                                 "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": 40}},
                                 "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Novo Nordisk A/S"}}}}
    fetch = fetch_by_url({"clinicaltrials.gov": {"studies": [study], "totalCount": 21}})
    monkeypatch.setattr(data_sources, "_fetch", fetch)
    data = await data_sources.clinical_trials(sponsor="Novo Nordisk", phase="Phase 3", started_after=f"{YEAR}-01-01",
                                              started_before=TODAY.isoformat(), limit=15)
    params = fetch.seen[0][1]
    assert params["query.spons"] == "Novo Nordisk" and params["sort"] == "StartDate:desc" and params["pageSize"] == 15
    assert params["filter.advanced"] == f"AREA[Phase]PHASE3 AND AREA[StartDate]RANGE[{YEAR}-01-01,{TODAY.isoformat()}]"
    assert data["total"] == 21 and data["trials"][0]["phase"] == "Phase 3" and data["trials"][0]["status"] == "not yet recruiting"
    with pytest.raises(DataSourceError):
        await data_sources.clinical_trials(sponsor="Novo", started_after="this year")


@pytest.mark.asyncio
async def test_pubmed_filters_by_year_and_leads_abstracts_with_findings(monkeypatch):
    xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>41</PMID><Article><Abstract>
      <AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">Heart failure is common.</AbstractText>
      <AbstractText Label="RESULTS" NlmCategory="RESULTS">HR 0.79 (95% CI 0.66-0.94).</AbstractText>
      <AbstractText Label="CONCLUSIONS" NlmCategory="CONCLUSIONS">GLP-1 RAs reduced events.</AbstractText>
    </Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    fetch = fetch_by_url({"esearch": {"esearchresult": {"idlist": ["41"], "count": "52"}},
                          "esummary": {"result": {"41": {"title": "GLP-1 and HF.", "fulljournalname": "JAMA", "pubdate": "2026 Sep",
                                                         "authors": [{"name": "Ostrominski J"}], "pubtype": ["Meta-Analysis"]}}},
                          "efetch": xml})
    monkeypatch.setattr(data_sources, "_fetch", fetch)
    data = await data_sources.pubmed("GLP-1 heart failure", since_year=2024)
    assert fetch.seen[0][1]["mindate"] == "2024" and fetch.seen[0][1]["datetype"] == "pdat"
    assert data["articles"][0]["abstract"].startswith("CONCLUSIONS: GLP-1 RAs reduced events. RESULTS: HR 0.79")
    await data_sources.pubmed("GLP-1", since_year=1200)          # out of range: no date filter
    assert "mindate" not in fetch.seen[-3][1]


# ── Tools ─────────────────────────────────────────────────────────────────────────────────────────

def toolbox(allowed=None, space=None):
    ctx = toolkit.RunContext(queue=asyncio.Queue(), space=space)
    tools = {t.name: t for t in toolkit.build_tools(ctx, tuple(allowed or space_templates.TOOL_LABELS))}
    return ctx, tools


def drain(queue):
    events = []
    while not queue.empty():
        events.append(json.loads(queue.get_nowait()[6:]))
    return events


def test_every_template_tool_is_implemented_and_labelled():
    _, tools = toolbox()
    assert set(tools) == set(space_templates.TOOL_LABELS)
    for template in space_templates.TEMPLATES:
        assert set(template.tools) <= set(tools), template.id
        assert len(template.starters) == 3 and template.brief and template.instructions
        assert space_templates.toolset(template.id, web_search=False) == ()
    assert space_templates.toolset(None) == space_templates.GENERAL_TOOLS


@pytest.mark.asyncio
async def test_trial_results_separate_started_from_planned_trials():
    future = (TODAY + timedelta(days=13)).isoformat()
    trial = lambda nct, start: {"nct_id": nct, "title": "Study", "phase": "Phase 3", "status": "recruiting", "sponsor": "Novo Nordisk",
                                "start": start, "primary_completion": "2028-01", "enrollment": 300, "conditions": ["Obesity"]}
    listed = {"total": 22, "trials": [trial("NCT1", future), trial("NCT2", f"{YEAR}-03-01")],
              "sources": [data_sources._source(n, f"https://clinicaltrials.gov/study/{n}") for n in ("NCT1", "NCT2")]}
    begun = {"total": 21, "trials": [], "sources": []}
    ctx, tools = toolbox(["clinical_trials"])
    with patch.object(data_sources, "clinical_trials", AsyncMock(side_effect=[listed, begun])) as search:
        out = await tools["clinical_trials"].ainvoke({"sponsor": "Novo Nordisk", "phase": "Phase 3",
                                                      "started_after": f"{YEAR}-01-01", "started_before": f"{YEAR + 1}-01-01"})
    assert search.await_args_list[1].args[5] == TODAY.isoformat()
    assert "22 trials match these filters: 21 have already started" in out and "1 are planned" in out
    assert f"PLANNED start {future} (not yet started)" in out and f"started {YEAR}-03-01" in out
    assert "The first 2" in out and "20 more match but are not shown" in out
    # The listed range is stated, so the earliest listed start is never presented as the earliest of all.
    assert f"started between {YEAR}-03-01 and {future}" in out and "do not call any listed date the earliest" in out
    labels = [e["label"] for e in drain(ctx.queue) if e["type"] == "agent_step"]
    assert labels[0] == f"Searching ClinicalTrials.gov: Novo Nordisk · phase 3 · started {YEAR}-01-01 to {YEAR + 1}-01-01"
    # A window that ends today or earlier needs no second count.
    with patch.object(data_sources, "clinical_trials", AsyncMock(return_value={**listed, "total": 2})) as search:
        out = await tools["clinical_trials"].ainvoke({"sponsor": "Novo Nordisk", "started_after": f"{YEAR}-01-01",
                                                      "started_before": TODAY.isoformat()})
    assert search.await_count == 1 and "All 2 are listed" in out


@pytest.mark.asyncio
async def test_economic_results_mark_projections_and_rank_countries():
    data = {"indicator": "gdp_growth", "label": "Real GDP growth (annual %)", "unit": "%", "provider": "IMF", "projections_from": YEAR,
            "series": {"Germany": [("2024", 0.0), (str(YEAR), 1.3)], "France": [("2024", 1.4), (str(YEAR), 0.4)],
                       "Italy": [("2024", 0.8), (str(YEAR), 0.8)]},
            "source": data_sources._source("IMF World Economic Outlook: Real GDP growth", "https://www.imf.org/external/datamapper/NGDP_RPCH")}
    ctx, tools = toolbox(["economic_data"])
    with patch.object(data_sources, "economic_indicator", AsyncMock(return_value=data)):
        out = await tools["economic_data"].ainvoke({"countries": ["DEU", "FRA", "ITA"], "indicator": "gdp_growth",
                                                    "start_year": 2024, "end_year": YEAR})
    assert out.startswith("IMF World Economic Outlook, Real GDP growth (annual %) [1]") and f"{YEAR} 1.3*" in out
    assert f"IMF projection (from {YEAR} on)" in out
    assert f"Ranking in {YEAR}*, highest first: Germany 1.3 > Italy 0.8 > France 0.4" in out
    assert "Ranking by average, highest first: France 0.9 > Italy 0.8 > Germany 0.65" in out
    assert [d.source for d in ctx.datasets.values()] == ["IMF World Economic Outlook"] * 3


@pytest.mark.asyncio
async def test_price_summaries_state_where_the_latest_close_sits():
    ctx, tools = toolbox(["stock_prices"])
    with patch.object(data_sources, "stock_history", AsyncMock(return_value=stock())):
        out = await tools["stock_prices"].ainvoke({"ticker": "AAPL"})
    assert "Latest is 0.03% below the period high. Latest is 36.4% above the period low." in out
    assert "end-of-day closes, not live quotes" in out and "Dataset d1" in out
    peak = stock(points=POINTS[:3])
    assert "The latest close IS the period high." in toolkit._position(peak["summary"])


@pytest.mark.asyncio
async def test_sources_keep_one_number_per_url_across_tools():
    ctx = toolkit.RunContext(queue=asyncio.Queue())
    first = ctx.add_sources([{"title": "A", "url": "https://a.test/1", "domain": "a.test"}, {"title": "B", "url": "https://b.test", "domain": "b.test"}])
    again = ctx.add_sources([{"title": "B again", "url": "https://b.test", "domain": "b.test"}, {"title": "C", "url": "https://c.test", "domain": "c.test"}])
    assert (first, again) == ([1, 2], [2, 3])
    assert [s["citationIndex"] for s in drain(ctx.queue)[-1]["sources"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_automatic_chart_draws_fetched_series_once():
    ctx = toolkit.RunContext(queue=asyncio.Queue())
    assert await toolkit.auto_chart(ctx) == ""
    ctx.add_dataset("Apple Inc. (AAPL)", POINTS, "USD", "date", "Yahoo Finance", data_sources.summarize_series(POINTS))
    assert "is ready" in await toolkit.auto_chart(ctx)
    assert await toolkit.auto_chart(ctx) == "" and len(ctx.charts) == 1
    tokens = [e["content"] for e in drain(ctx.queue) if e["type"] == "token"]
    assert len(tokens) == 1 and tokens[0].startswith(':::artifact{type="react" title="Apple Inc. (AAPL)"}')
    # When every series measures the same thing, the title says what is plotted.
    ctx = toolkit.RunContext(queue=asyncio.Queue())
    for country in ("Germany", "France"):
        ctx.add_dataset(country, [("2024", 0.2), ("2025", 0.4)], "%", "year", "IMF", topic="Real GDP growth (annual %)")
    await toolkit.auto_chart(ctx)
    assert ctx.charts[0].startswith(':::artifact{type="react" title="Real GDP growth (annual %): Germany vs France"}')


# ── Charts ────────────────────────────────────────────────────────────────────────────────────────

def test_charts_rebase_series_that_cannot_share_an_axis_and_rank_their_changes():
    lly = charts.Dataset("d1", "Eli Lilly (LLY)", [("2025-10-13", 819.4), ("2026-10-12", 1182.62)], "USD", "date", "Yahoo Finance",
                         {"change_pct": 44.33})
    nvo = charts.Dataset("d2", "Novo Nordisk (NVO)", [("2025-10-13", 57.5), ("2026-10-12", 38.58)], "USD", "date", "Yahoo Finance",
                         {"change_pct": -32.9})
    artifact, description = charts.build_chart([nvo, lly], "LLY vs NVO")
    assert "rebased to 100" in description and "Eli Lilly (LLY) +44.33% > Novo Nordisk (NVO) -32.90%" in description
    spec = json.loads(re.search(r"^const SPEC = (.*);$", artifact, re.M).group(1))
    assert spec["unit"] == "index" and [s["name"] for s in spec["series"]] == ["Novo Nordisk (NVO)", "Eli Lilly (LLY)"]
    assert [row["s1"] for row in spec["rows"]] == [100.0, round(1182.62 / 819.4 * 100, 3)]
    eur = charts.Dataset("d3", "EUR/USD", [("2026-01-02", 1.03), ("2026-10-12", 1.12)], "USD", "date", "ECB")
    gbp = charts.Dataset("d4", "EUR/GBP", [("2026-01-02", 0.83), ("2026-10-12", 0.86)], "GBP", "date", "ECB")
    assert "rebased" in charts.build_chart([eur, gbp], "Euro")[1]
    year = charts.Dataset("d5", "Germany", [("2024", 0.0), ("2025", 0.2)], "%", "year", "IMF")
    with pytest.raises(ValueError):
        charts.build_chart([eur, year], "Mixed")


def test_chart_titles_cannot_break_out_of_the_artifact_header():
    data = charts.Dataset("d1", "A", POINTS, "USD", "date", "Yahoo Finance", data_sources.summarize_series(POINTS))
    artifact, _ = charts.build_chart([data], 'Apple "}\n:::\n<script>alert(1)</script>')
    header = artifact.split("\n", 1)[0]
    assert re.fullmatch(r':::artifact\{type="react" title="[^"{}\n]*"\}', header), header
    assert artifact.rstrip().endswith("\n:::") and artifact.count("\n:::") == 1


# ── Templates, the API and the migration ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spaces_are_created_from_a_template_with_its_agent(api):  # noqa: F811
    owner = api(OWNER)
    listed = (await owner.get("/api/v1/spaces/templates")).json()
    assert [t["id"] for t in listed["items"]] == [t.id for t in space_templates.TEMPLATES]
    assert listed["featured"] == list(space_templates.FEATURED)
    data = next(t for t in listed["items"] if t["id"] == "tpl_data")
    assert {"id": "stock_prices", "label": "Stock prices"} in data["tools"] and len(data["starters"]) == 3
    space = (await owner.post("/api/v1/spaces", json={"template": "tpl_data"})).json()
    assert (space["name"], space["template"], space["icon"]) == ("Data Analyst", "tpl_data", "📈")
    assert space["instructions"] == space_templates.get("tpl_data").instructions
    assert space["agent"]["template"] == {"id": "tpl_data", "name": "Data Analyst"}
    assert [t["id"] for t in space["agent"]["tools"]] == list(space_templates.get("tpl_data").tools)
    assert space["agent"]["starters"] == list(space_templates.get("tpl_data").starters)
    # Turning web search off leaves the Space's files only, so its agent has no tools.
    updated = (await owner.patch(f"/api/v1/spaces/{space['id']}", json={"webSearch": False, "expected_revision": space["revision"]})).json()
    assert updated["agent"]["tools"] == []
    named = (await owner.post("/api/v1/spaces", json={"template": "tpl_trip", "name": "Lisbon in May"})).json()
    assert (named["name"], named["template"]) == ("Lisbon in May", "tpl_trip")
    custom = (await owner.post("/api/v1/spaces", json={"name": "Board prep"})).json()
    assert custom["template"] is None and custom["agent"]["template"] is None and custom["agent"]["tools"]
    for body in ({}, {"template": "tpl_unknown"}, {"name": "  "}):
        assert (await owner.post("/api/v1/spaces", json=body)).status_code == 422, body


def test_migration_recognizes_existing_template_spaces_and_is_reversible():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0006_space_templates.py"
    spec = importlib.util.spec_from_file_location("migration_0006", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    # The frozen openings still match the templates, so existing template Spaces are recognized.
    for template_id, name, opening in migration.TEMPLATES:
        template = space_templates.get(template_id)
        assert template.name == name and template.instructions.startswith(opening), template_id
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE spaces (id INTEGER PRIMARY KEY, name TEXT, custom_instructions TEXT)"))
        connection.execute(sa.text("INSERT INTO spaces (name, custom_instructions) VALUES "
                                   "('My numbers', :data), (' data analyst ', 'Custom'), ('Board prep', 'Be brief.')"),
                           {"data": space_templates.get("tpl_data").instructions})
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        rows = connection.execute(sa.text("SELECT name, template FROM spaces ORDER BY id")).all()
        assert rows == [("My numbers", "tpl_data"), (" data analyst ", "tpl_data"), ("Board prep", None)]
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "template" not in [column["name"] for column in sa.inspect(connection).get_columns("spaces")]


# ── Regressions found in review ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_loosely_typed_tool_arguments_are_normalized_instead_of_rejected():
    # Models send 3 for "3", one string for a list, "2015" for a year and "true" for a flag.
    ctx, tools = toolbox()
    trials = AsyncMock(return_value={"total": 0, "trials": [], "sources": []})
    economy = AsyncMock(side_effect=DataSourceError("stub"))
    rates = AsyncMock(side_effect=DataSourceError("stub"))
    papers = AsyncMock(return_value={"total": 0, "articles": [], "sources": []})
    with patch.object(data_sources, "clinical_trials", trials), patch.object(data_sources, "economic_indicator", economy), \
         patch.object(data_sources, "exchange_rates", rates), patch.object(data_sources, "pubmed", papers):
        await tools["clinical_trials"].ainvoke({"sponsor": "Novo Nordisk", "phase": 3})
        await tools["economic_data"].ainvoke({"countries": "DEU, FRA", "indicator": "gdp_growth", "start_year": "2015", "end_year": 2025})
        await tools["exchange_rates"].ainvoke({"base": "USD", "symbols": "EUR,JPY"})
        await tools["pubmed"].ainvoke({"query": "glp-1", "newest_first": "true", "since_year": "2024"})
        out = await tools["create_chart"].ainvoke({"dataset_ids": "d9", "title": "x"})
    assert trials.await_args.args[3] == "3"
    assert economy.await_args.args == (["DEU", "FRA"], "gdp_growth", 2015, 2025)
    assert rates.await_args.args[1] == ["EUR", "JPY"]
    assert papers.await_args.kwargs == {"limit": 5, "newest_first": True, "since_year": 2024}
    assert "Unknown dataset ids d9" in out
    # The published schemas accept those forms, so the provider's own argument check passes too.
    schema = json.dumps(tools["economic_data"].tool_call_schema.model_json_schema())
    assert '"type": "string"' in schema and '"type": "array"' in schema


def test_lists_and_country_names_are_understood():
    assert toolkit._as_list("Germany, France and Italy") == ["Germany", "France", "Italy"]
    assert toolkit._as_list("EUR JPY") == ["EUR", "JPY"] and toolkit._as_list("d1 d2") == ["d1", "d2"]
    for name in ("Sri Lanka", "United Kingdom", "Hong Kong"):
        assert toolkit._as_list(name) == [name]
    for given, code in [("Germany", "DEU"), ("the United Kingdom", "GBR"), ("UK", "GBR"), ("USA", "USA"), ("us", "USA"),
                        ("South Korea", "KOR"), ("Sri Lanka", "LKA"), ("de", "DE"), ("ITA", "ITA")]:
        assert data_sources.country_code(given) == code, given
    with pytest.raises(DataSourceError, match="Unknown country 'Atlantis'"):
        data_sources.country_code("Atlantis")


@pytest.mark.asyncio
async def test_economic_data_accepts_country_names(monkeypatch):
    imf = {"values": {"NGDP_RPCH": {"DEU": {"2024": 0.0}, "GBR": {"2024": 1.1}}}}
    countries = {"countries": {"DEU": {"label": "Germany"}, "GBR": {"label": "United Kingdom"}}}
    monkeypatch.setattr(data_sources, "_fetch", fetch_by_url({"v1/countries": countries, "v1/NGDP_RPCH": imf}))
    data = await data_sources.economic_indicator(["Germany", "the UK", "germany"], "gdp_growth", 2024, 2024)
    assert list(data["series"]) == ["Germany", "United Kingdom"]


def test_periods_are_understood_or_refused_never_silently_replaced():
    for given, expected in [("1Y", "1y"), ("1 year", "1y"), ("12mo", "1y"), ("6 months", "6m"), ("YTD", "ytd"),
                            ("30d", "1m"), ("3y", "5y"), ("max", "max"), (None, "6m"), ("2Y", "2y")]:
        assert data_sources.normalize_period(given) == expected, given
    with pytest.raises(DataSourceError, match="1m, 3m, 6m"):
        data_sources.normalize_period("fortnightly")


def test_dates_accept_years_and_months_as_range_bounds():
    assert data_sources.normalize_day("2026") == "2026-01-01"
    assert data_sources.normalize_day("2026", end=True) == "2026-12-31"
    assert data_sources.normalize_day("2028-02", end=True) == "2028-02-29"
    assert data_sources.normalize_day("2026/3/7") == "2026-03-07"
    assert data_sources.normalize_day(" ") is None
    for bad in ("last month", "2026-13", "2026-02-30"):
        with pytest.raises(DataSourceError):
            data_sources.normalize_day(bad)


@pytest.mark.asyncio
async def test_a_year_only_trial_window_still_separates_started_from_planned():
    listed = {"total": 22, "trials": [{"nct_id": "NCT1", "title": "T", "phase": "Phase 3", "status": "recruiting", "sponsor": "S",
                                       "start": f"{YEAR}-03-01", "primary_completion": "", "enrollment": 1, "conditions": []}],
              "sources": [data_sources._source("NCT1", "https://clinicaltrials.gov/study/NCT1")]}
    _, tools = toolbox(["clinical_trials"])
    with patch.object(data_sources, "clinical_trials", AsyncMock(side_effect=[listed, {**listed, "total": 21}])) as search:
        out = await tools["clinical_trials"].ainvoke({"sponsor": "S", "started_after": str(YEAR), "started_before": str(YEAR)})
    assert search.await_args_list[0].args[4:6] == (f"{YEAR}-01-01", f"{YEAR}-12-31")
    assert search.await_args_list[1].args[5] == TODAY.isoformat() and "21 have already started" in out


@pytest.mark.asyncio
async def test_a_malformed_fda_date_is_reported_not_replaced_by_the_last_month(monkeypatch):
    monkeypatch.setattr(data_sources, "_fetch", fetch_by_url({"api.fda.gov": {"results": []}}))
    with pytest.raises(DataSourceError, match="Dates must look like"):
        await data_sources.fda_approvals(approved_since="sometime")


@pytest.mark.asyncio
async def test_when_yahoo_fails_and_the_fallback_cannot_help_the_real_reason_is_reported(monkeypatch):
    # Stooq answers cloud hosts with an HTML check page; that must not turn into "no data for AAPL".
    monkeypatch.setattr(data_sources, "_fetch", fetch_by_url({
        "finance.yahoo.com": DataSourceError("query1.finance.yahoo.com is limiting requests right now. Try again in a minute."),
        "stooq.com": "<!DOCTYPE html><html><body><noscript>Enable JavaScript</noscript></body></html>"}))
    with pytest.raises(DataSourceError, match="limiting requests"):
        await data_sources.stock_history("AAPL", "1m")


@pytest.mark.asyncio
async def test_exchange_rates_use_the_current_frankfurter_api(monkeypatch):
    fetch = fetch_by_url({"api.frankfurter.dev/v1/latest": {"date": "2026-10-12", "rates": {"EUR": 0.89437}}})
    monkeypatch.setattr(data_sources, "_fetch", fetch)
    data = await data_sources.exchange_rates("usd", ["eur"])
    assert data["rates"] == {"EUR": 0.89437} and fetch.seen[0][0] == "https://api.frankfurter.dev/v1/latest"


def test_follow_ups_keep_the_previous_answer_text_after_a_chart():
    chart = charts.build_chart([charts.Dataset("d1", "Apple Inc. (AAPL)", POINTS, "USD", "date", "Yahoo Finance",
                                               data_sources.summarize_series(POINTS))], "Apple (AAPL) share price")[0]
    answer = chart + "\n\nApple closed at $340.97, up 36.39% over six months [1]."
    model_written = ':::artifact{type="react" title="Revenue dashboard"}\nexport default function App() { return null }\n:::\nDone.'
    from src.services.conversation_memory import answer_context
    history = [{"role": "user", "content": "graph apple"}, {"role": "assistant", "content": answer},
               {"role": "user", "content": "build a dashboard"}, {"role": "assistant", "content": model_written}]
    kept = answer_context(history, "explain that")
    assert kept[1]["content"] == "[Chart shown: Apple (AAPL) share price]\n\nApple closed at $340.97, up 36.39% over six months [1]."
    assert kept[3]["content"] == model_written            # a model-written artifact stays editable


@pytest.mark.asyncio
async def test_attached_documents_reach_the_agent_without_being_cut():
    passage = "Opening summary. " + "Filler text. " * 600 + "The relevant figure is 42 million euros."
    runtime = FakeRuntime(text("42 million euros [1]."))
    await run_agent("what is the figure?", data_space(), runtime,
                    attachments=[{"title": "report.pdf", "url": "/api/v1/attachments/a1/content", "domain": "attachment",
                                  "snippet": passage}])
    assert "The relevant figure is 42 million euros." in runtime.calls[0]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_silent_stretches_send_keepalives(monkeypatch):
    monkeypatch.setattr(space_agent, "HEARTBEAT_SECONDS", 0.05)

    async def slow(*_args):
        await asyncio.sleep(0.3)
        return stock()
    runtime = FakeRuntime(tool("stock_prices", {"ticker": "AAPL"}), text("Done."))
    with patch.object(data_sources, "stock_history", slow):
        events = await run_agent("apple", data_space(), runtime, raw=True)
    assert ": keepalive\n\n" in events and any('"Done."' in e for e in events)


@pytest.mark.asyncio
async def test_a_rejected_model_call_degrades_to_an_answer_without_tools(monkeypatch):
    monkeypatch.setattr("src.services.agents.chat_model.asyncio.sleep", AsyncMock())
    rejected = lambda: LLMProviderError("The AI provider rejected this request.")
    runtime = FakeRuntime(rejected(), rejected(), text("I could not fetch live prices just now."))
    events = await run_agent("graph apple", data_space(), runtime)
    assert answer_text(events) == "I could not fetch live prices just now." and not any(e["type"] == "error" for e in events)
    assert runtime.calls[1]["temperature"] == 0.6                      # the retry varies the generation
    final = runtime.calls[2]
    assert "tools" not in final and "Tools are unavailable" in final["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_agent_setup_failures_never_show_internal_errors():
    with patch.object(space_agent, "agent_model", lambda _mode: (_ for _ in ()).throw(LLMProviderError("No AI provider is configured."))):
        events = [json.loads(e[6:]) async for e in space_agent.run_space_agent("q", [], data_space(), TurnContext())]
    assert events == [{"type": "error", "message": "No AI provider is configured.", "code": "llm_unavailable"}]
    # A configured model (independent of any local .env), then an unexpected internal failure.
    model = CortenChatModel(runtime=FakeRuntime(), model="openai/gpt-oss-120b")
    with patch.object(space_agent, "agent_model", lambda _mode: model), \
         patch.object(space_agent, "build_tools", side_effect=KeyError("secret internal detail")):
        events = [json.loads(e[6:]) async for e in space_agent.run_space_agent("q", [], data_space(), TurnContext())]
    assert events == [{"type": "error", "message": "The Space agent could not start. Please try again."}]


@pytest.mark.asyncio
async def test_quota_errors_carry_the_retry_time_like_standard_answers():
    events = await run_agent("q", data_space(), FakeRuntime(LLMQuotaError(90), LLMQuotaError(90)))
    error = next(e for e in events if e["type"] == "error")
    assert error["code"] == "llm_rate_limited" and error["retry_after_seconds"] == 90


@pytest.mark.asyncio
async def test_a_dataset_listed_twice_is_drawn_once():
    ctx, tools = toolbox(["create_chart"])
    ctx.add_dataset("Apple", POINTS, "USD", "date", "Yahoo Finance", data_sources.summarize_series(POINTS))
    await tools["create_chart"].ainvoke({"dataset_ids": ["d1", "d1 "], "title": "Apple"})
    spec = json.loads(re.search(r"^const SPEC = (.*);$", ctx.charts[0], re.M).group(1))
    assert len(spec["series"]) == 1
