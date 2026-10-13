"""The tools a Space agent can use, built per question.

Every tool validates its input, runs with a time limit, reports a visible step to the user, numbers the sources it
found so the answer can cite them, and returns compact text so the model's context (and the shared provider quota)
is not wasted. Failures come back as plain explanations the model can act on, never as exceptions.
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from urllib.parse import urlsplit

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.services.agents import data_sources
from src.services.agents.charts import Dataset, build_chart
from src.services.agents.data_sources import DataSourceError
from src.services.agents.space_templates import TOOL_LABELS

logger = logging.getLogger(__name__)
TOOL_TIMEOUT = 35
SNIPPET = 380


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


@dataclass
class RunContext:
    """Everything one agent run shares between its tools and the event stream."""
    queue: asyncio.Queue
    space: Any = None
    domains: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    datasets: dict[str, Dataset] = field(default_factory=dict)
    charts: list[str] = field(default_factory=list)
    steps: int = 0
    used: set = field(default_factory=set)
    memo: dict = field(default_factory=dict)   # identical calls in one run return the earlier result

    def add_sources(self, items: list[dict]) -> list[int]:
        """Number sources across the whole answer; the same URL keeps its number."""
        numbers = []
        for item in items:
            url = item.get("url") or ""
            existing = next((s for s in self.sources if url and s["url"] == url), None)
            if existing is None:
                existing = {**item, "citationIndex": len(self.sources) + 1,
                            "favicon": f"https://www.google.com/s2/favicons?domain={item.get('domain', '')}&sz=128"}
                self.sources.append(existing)
            numbers.append(existing["citationIndex"])
        if items:
            previews = [{**s, "snippet": (s.get("snippet") or "")[:600]} for s in self.sources]
            self.queue.put_nowait(_sse("sources", {"sources": previews, "items": previews}))
        return numbers

    def add_dataset(self, label: str, points: list, unit: str, x_kind: str, source: str, summary: dict | None = None) -> str:
        dataset_id = f"d{len(self.datasets) + 1}"
        self.datasets[dataset_id] = Dataset(dataset_id, label, points, unit, x_kind, source, summary or {})
        return dataset_id

    @asynccontextmanager
    async def step(self, tool: str, label: str):
        """A visible step: running, then done with a detail, or failed with the reason."""
        self.steps += 1
        self.used.add(tool)
        step = {"id": f"step-{self.steps}", "tool": tool, "label": label}
        started = time.monotonic()
        self.queue.put_nowait(_sse("agent_step", {**step, "status": "running"}))
        outcome = {"detail": "", "failed": False}
        try:
            yield outcome
        except Exception as error:
            outcome.update(failed=True, detail=outcome["detail"] or _reason(error))
            raise
        finally:
            self.queue.put_nowait(_sse("agent_step", {**step, "status": "failed" if outcome["failed"] else "done",
                                                      "detail": outcome["detail"][:160],
                                                      "ms": round((time.monotonic() - started) * 1000)}))


def _reason(error: Exception) -> str:
    if isinstance(error, DataSourceError):
        return str(error)
    if isinstance(error, asyncio.TimeoutError):
        return "The source took too long to respond."
    return "The tool failed unexpectedly."


def _cite(numbers: list[int]) -> str:
    return "".join(f"[{n}]" for n in numbers)


def _fmt(value: float) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.4g}" if abs(value) < 10 else f"{value:,.2f}"


def _position(s: dict) -> str:
    """Where the latest value sits in the period, computed here so the model never has to eyeball a trend."""
    if not s["high"] or not s["low"]:
        return ""
    from_high = (s["last"] - s["high"]) / s["high"] * 100
    from_low = (s["last"] - s["low"]) / s["low"] * 100
    peak = ("The latest close IS the period high." if s["end"] == s["high_date"] else
            f"Latest is {abs(from_high):.2f}% below the period high." if abs(from_high) < 1 else
            f"Latest is {abs(from_high):.1f}% below the period high.")
    trough = " The latest close IS the period low." if s["end"] == s["low_date"] else f" Latest is {from_low:.1f}% above the period low."
    swing = f" High-to-low range is {(s['high'] - s['low']) / s['low'] * 100:.1f}% of the low."
    return peak + trough + swing


def _comparison(series: dict[str, list[tuple[str, float]]], projections_from: int | None = None) -> str:
    """Averages, extremes and the latest ranking across countries, computed here so comparisons are never misread."""
    mark = lambda year: f"{year}*" if projections_from and int(year) >= projections_from else str(year)
    lines = []
    for name, points in series.items():
        values = [value for _, value in points]
        high, low = max(points, key=lambda p: p[1]), min(points, key=lambda p: p[1])
        lines.append(f"{name}: average {_fmt(sum(values) / len(values))} over {points[0][0]}–{mark(points[-1][0])}; "
                     f"high {_fmt(high[1])} ({mark(high[0])}); low {_fmt(low[1])} ({mark(low[0])}); latest {_fmt(points[-1][1])} ({mark(points[-1][0])})")
    common = set.intersection(*(set(year for year, _ in points) for points in series.values())) if len(series) > 1 else set()
    if common:
        year = max(common)
        ranked = sorted(((dict(points)[year], name) for name, points in series.items()), reverse=True)
        lines.append(f"Ranking in {mark(year)}, highest first: " + " > ".join(f"{name} {_fmt(value)}" for value, name in ranked))
        averages = sorted(((sum(v for _, v in points) / len(points), name) for name, points in series.items()), reverse=True)
        lines.append("Ranking by average, highest first: " + " > ".join(f"{name} {_fmt(value)}" for value, name in averages))
    return "\nComputed summary:\n" + "\n".join(lines)


def _sample(points: list[tuple[str, float]], count: int = 12) -> str:
    if len(points) <= count:
        chosen = points
    else:
        step = (len(points) - 1) / (count - 1)
        chosen = [points[round(i * step)] for i in range(count)]
    return ", ".join(f"{x}: {_fmt(y)}" for x, y in chosen)


async def auto_chart(ctx: RunContext) -> str:
    """Chart the fetched series when the agent did not (it ran out of steps or forgot). Returns the chart's
    description for the model, or "" when there is nothing to draw."""
    if ctx.charts or not ctx.datasets:
        return ""
    latest = list(ctx.datasets.values())[-1]
    chosen = [d for d in ctx.datasets.values() if d.x_kind == latest.x_kind][-4:]
    title = " vs ".join(d.label for d in chosen)[:100]
    try:
        async with ctx.step("create_chart", "Drawing the chart") as outcome:
            artifact, description = build_chart(chosen, title)
            ctx.charts.append(artifact)
            ctx.queue.put_nowait(_sse("token", {"content": artifact + "\n\n"}))
            outcome["detail"] = title[:80]
    except Exception:
        logger.exception("[SpaceAgent] Automatic chart failed")
        return ""
    return description


# ── Argument schemas (they become the tools' JSON schemas for the model) ────────────────────────────
class SearchArgs(BaseModel):
    query: str = Field(description="What to search for, written as a search engine query.")


class UrlArgs(BaseModel):
    url: str = Field(description="Full http(s) URL of the page to read.")


class FilesArgs(BaseModel):
    query: str = Field(description="What to look for in the Space's files. Use 'overview' to get the start of each file.")


class CalcArgs(BaseModel):
    expression: str = Field(description="Arithmetic expression, e.g. (340.97 - 255.4) / 255.4 * 100")


class StockArgs(BaseModel):
    ticker: str = Field(description="Exchange ticker symbol, e.g. AAPL, MSFT, LLY, NOVO-B.CO, ^GSPC for the S&P 500.")
    period: str = Field(default="6m", description="One of 1m, 3m, 6m, ytd, 1y, 2y, 5y, 10y, max.")


class FxArgs(BaseModel):
    base: str = Field(description="Three-letter base currency, e.g. EUR.")
    symbols: list[str] = Field(description="Three-letter target currencies, e.g. ['USD', 'GBP'].")
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD for a history from this date; omit for today's rates.")
    end_date: Optional[str] = Field(default=None, description="YYYY-MM-DD end of the history; omit for today.")


class EconomyArgs(BaseModel):
    countries: list[str] = Field(description="Three-letter ISO country codes, e.g. ['DEU', 'FRA', 'ITA']. Up to 6.")
    indicator: str = Field(description="One of: " + ", ".join(data_sources.INDICATORS))
    start_year: int = Field(description="First year, e.g. 2015.")
    end_year: int = Field(description="Last year, e.g. 2025. Later years return IMF projections where available.")


class TrialsArgs(BaseModel):
    query: Optional[str] = Field(default=None, description="Condition, drug or intervention, e.g. 'semaglutide obesity'.")
    sponsor: Optional[str] = Field(default=None, description="Sponsor company, e.g. 'Novo Nordisk'. Use this for a company's own trials.")
    status: Optional[str] = Field(default=None, description="Optional: recruiting, active, completed, not_yet_recruiting, terminated.")
    phase: Optional[str] = Field(default=None, description="Optional trial phase: 1, 2, 3 or 4.")
    started_after: Optional[str] = Field(default=None, description="Optional YYYY-MM-DD: only trials starting on or after this date.")
    started_before: Optional[str] = Field(default=None, description="Optional YYYY-MM-DD: only trials starting on or before this date (use today for trials that have already started).")


class LiteratureArgs(BaseModel):
    query: str = Field(description="Search terms, e.g. 'GLP-1 receptor agonists heart failure'.")
    newest_first: bool = Field(default=False, description="True to list the most recent publications first.")


class PubmedArgs(LiteratureArgs):
    query: str = Field(description="Plain search terms, e.g. 'GLP-1 receptor agonists heart failure randomized'. No date syntax.")
    since_year: Optional[int] = Field(default=None, description="Only articles published in or after this year, e.g. 2024.")


class FdaArgs(BaseModel):
    drug: Optional[str] = Field(default=None, description="Brand or generic name or sponsor, e.g. 'Mounjaro'. Omit to list recent approvals.")
    approved_since: Optional[str] = Field(default=None, description="YYYY-MM-DD; with no drug, list new NDA/BLA approvals since this date.")


class WeatherArgs(BaseModel):
    location: str = Field(description="City, optionally with country, e.g. 'Lisbon, Portugal'.")


class ChartArgs(BaseModel):
    dataset_ids: list[str] = Field(description="Dataset ids returned by data tools, e.g. ['d1'] or ['d1', 'd2'].")
    title: str = Field(description="Short chart title, e.g. 'Apple (AAPL) share price, last 6 months'.")
    chart_type: str = Field(default="auto", description="auto, line, area or bar.")
    rebase_to_100: bool = Field(default=False, description="True to compare series with different scales or currencies.")


def build_tools(ctx: RunContext, allowed: tuple[str, ...]) -> list[StructuredTool]:
    """The run's tools, limited to the Space's toolset."""

    async def guarded(tool: str, label: str, work, **args) -> str:
        key = tool + json.dumps(args, sort_keys=True, default=str)
        if key in ctx.memo:
            # Models sometimes repeat a call verbatim; repeating the request would only spend time and quota.
            return "You already called this with the same arguments; the result was:\n" + ctx.memo[key]
        try:
            async with ctx.step(tool, label) as outcome:
                text, detail = await asyncio.wait_for(work(), TOOL_TIMEOUT)
                outcome["detail"] = detail
        except (DataSourceError, asyncio.TimeoutError) as error:
            text = f"{TOOL_LABELS[tool]} could not answer: {_reason(error)} Answer with what you have, or try another tool."
        except Exception:
            logger.exception("[SpaceAgent] Tool %s failed", tool)
            text = f"{TOOL_LABELS[tool]} failed unexpectedly. Answer with what you have, or try another tool."
        ctx.memo[key] = text
        return text

    # Web ─────────────────────────────────────────────────────────────────────────────────────────
    async def web_search(query: str) -> str:
        async def work():
            from src.services.web_search_service import tavily_search_service
            from src.tools.search.web_search_tool import allowed_domain
            if not tavily_search_service.client:
                raise DataSourceError("Web search is not configured.")
            searches = [tavily_search_service.search(query[:300], max_results=6)]
            if ctx.domains:
                searches.append(tavily_search_service.search(query[:300], max_results=4, include_domains=ctx.domains[:10]))
            found = await asyncio.gather(*searches, return_exceptions=True)
            if isinstance(found[0], BaseException) and (len(found) == 1 or isinstance(found[1], BaseException)):
                raise DataSourceError("Web search is unavailable right now.")
            preferred = [r for r in (found[1].get("results", []) if len(found) > 1 and isinstance(found[1], dict) else [])
                         if allowed_domain(r.get("url", ""), ctx.domains)]
            general = found[0].get("results", []) if isinstance(found[0], dict) else []
            seen, results = set(), []
            for result in preferred + general:
                if result.get("url") and result["url"] not in seen and (result.get("snippet") or "").strip():
                    seen.add(result["url"])
                    results.append(result)
            results = results[:6]
            if not results:
                return "No web results found. Try different search terms.", "No results"
            numbers = ctx.add_sources([{"title": r["title"], "url": r["url"], "domain": r.get("domain", ""),
                                        "snippet": r["snippet"]} for r in results])
            lines = [f"[{n}] {r['title']} ({r.get('domain', '')})\n{r['snippet'][:SNIPPET]}" for n, r in zip(numbers, results)]
            domains = ", ".join(dict.fromkeys(r.get("domain", "") for r in results[:3]))
            return "\n\n".join(lines), f"{len(results)} results · {domains}"
        return await guarded("web_search", f"Searching the web for “{query[:70]}”", work, query=query.strip().lower())

    async def read_webpage(url: str) -> str:
        async def work():
            from src.services.web_search_service import tavily_search_service
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise DataSourceError("Give a full http(s) URL.")
            text = await tavily_search_service.extract(url)
            if not text.strip():
                raise DataSourceError("That page could not be read.")
            host = parts.hostname.removeprefix("www.")
            [number] = ctx.add_sources([{"title": f"{host}{parts.path[:60]}", "url": url, "domain": host, "snippet": text[:1500]}])
            return f"[{number}] {url}\n{text[:6000]}", f"Read {len(text):,} characters"
        return await guarded("read_webpage", f"Reading {urlsplit(url).hostname or 'the page'}", work, url=url)

    # Space files ───────────────────────────────────────────────────────────────────────────────────
    async def search_space_files(query: str) -> str:
        async def work():
            if not ctx.space or not ctx.space.has_files:
                return "This Space has no files yet.", "No files in this Space"
            broad = query.strip().lower() in ("overview", "summary", "all", "everything", "")
            passages = await ctx.space.retrieve(query, broad=broad)
            if not passages:
                return "No passages in this Space's files match. Try other words or 'overview'.", "No matching passages"
            numbers = ctx.add_sources(passages)
            return "\n\n".join(f"[{n}] {p['title']}\n{p['snippet'][:1800]}" for n, p in zip(numbers, passages)), \
                f"Passages from {len(passages)} file{'s' if len(passages) != 1 else ''}"
        return await guarded("search_space_files", "Searching this Space's files", work, query=query.strip().lower())

    # Calculator ────────────────────────────────────────────────────────────────────────────────────
    async def calculator(expression: str) -> str:
        async def work():
            from src.tools.compute.calculator_tool import CalculatorTool
            value = CalculatorTool()._safe_eval(expression[:300])
            if value is None:
                raise DataSourceError("That expression could not be calculated. Use numbers and + - * / ** ( ).")
            return f"{expression} = {value:,.10g}", f"= {value:,.6g}"
        return await guarded("calculator", "Calculating", work, expression=expression)

    # Markets and economy ───────────────────────────────────────────────────────────────────────────
    async def stock_prices(ticker: str, period: str = "6m") -> str:
        async def work():
            data = await data_sources.stock_history(ticker, period)
            [number] = ctx.add_sources([data["source"]])
            s = data["summary"]
            dataset = ctx.add_dataset(f"{data['name']} ({data['symbol']})", data["points"], data["currency"], "date",
                                      f"{data['provider']}, {data['exchange']}".strip(", "), s)
            cadence = {"1d": "daily", "1wk": "weekly", "1mo": "monthly"}.get(data["interval"], data["interval"])
            text = (f"Dataset {dataset}: {data['name']} ({data['symbol']}) {cadence} closing prices in {data['currency']} "
                    f"on {data['exchange']}, from {data['provider']}, {s['start']} to {s['end']}, {s['count']} points {_cite([number])}. "
                    "These are end-of-day closes, not live quotes.\n"
                    f"Latest {_fmt(s['last'])} on {s['end']}; change {_fmt(s['change'])} ({s['change_pct']}%) since {s['start']}; "
                    f"high {_fmt(s['high'])} on {s['high_date']}; low {_fmt(s['low'])} on {s['low_date']}.\n"
                    f"{_position(s)}\nSampled closes: {_sample(data['points'])}")
            return text, f"{s['count']} {'trading days' if data['interval'] == '1d' else 'points'} · last {_fmt(s['last'])} {data['currency']}"
        return await guarded("stock_prices", f"Fetching {ticker.upper()[:20]} prices ({period})", work,
                             ticker=ticker.strip().upper(), period=period)

    async def exchange_rates(base: str, symbols: list[str], start_date: str | None = None, end_date: str | None = None) -> str:
        async def work():
            data = await data_sources.exchange_rates(base, symbols, start_date, end_date)
            [number] = ctx.add_sources([data["source"]])
            if "series" in data:
                lines = []
                for symbol, points in data["series"].items():
                    s = data["summaries"][symbol]
                    dataset = ctx.add_dataset(f"{data['base']}/{symbol}", points, symbol, "date", "European Central Bank", s)
                    lines.append(f"Dataset {dataset}: 1 {data['base']} in {symbol}, {s['start']} to {s['end']}: latest {_fmt(s['last'])}, "
                                 f"change {s['change_pct']}%, high {_fmt(s['high'])} ({s['high_date']}), low {_fmt(s['low'])} ({s['low_date']}).")
                return "European Central Bank reference rates:\n" + "\n".join(lines) + f" {_cite([number])}", f"{len(data['series'])} series"
            rates = ", ".join(f"1 {data['base']} = {_fmt(v)} {k}" for k, v in data["rates"].items())
            return f"European Central Bank reference rates on {data['date']}: {rates} {_cite([number])}", rates[:80]
        return await guarded("exchange_rates", f"Fetching {base.upper()[:3]} exchange rates", work,
                             base=base, symbols=symbols, start=start_date, end=end_date)

    async def economic_data(countries: list[str], indicator: str, start_year: int, end_year: int) -> str:
        async def work():
            data = await data_sources.economic_indicator(countries, indicator, start_year, end_year)
            [number] = ctx.add_sources([data["source"]])
            first = data["projections_from"]
            source = "IMF World Economic Outlook" if data["provider"] == "IMF" else "World Bank"
            lines = []
            for country, points in data["series"].items():
                dataset = ctx.add_dataset(country, points, data["unit"], "year", source)
                lines.append(f"Dataset {dataset}: {country}: " + ", ".join(
                    f"{year} {_fmt(value)}{'*' if first and int(year) >= first else ''}" for year, value in points))
            note = (f"\n* = IMF projection (from {first} on), not an outcome; label projected years as projections."
                    if first and any(int(y) >= first for points in data["series"].values() for y, _ in points) else "")
            return (f"{source}, {data['label']} {_cite([number])}\n" + "\n".join(lines) + note
                    + _comparison(data["series"], first),
                    f"{source} · {data['label']} · {len(data['series'])} countries")
        return await guarded("economic_data", "Fetching economic data", work, countries=countries, indicator=indicator,
                             start=start_year, end=end_year)

    # Life sciences and research ──────────────────────────────────────────────────────────────────────
    async def clinical_trials(query: str | None = None, sponsor: str | None = None, status: str | None = None,
                              phase: str | None = None, started_after: str | None = None, started_before: str | None = None) -> str:
        async def work():
            today = date.today().isoformat()
            search = data_sources.clinical_trials(query, sponsor, status, phase, started_after, started_before, limit=15)
            # A date window reaching past today mixes trials that have started with planned ones; count them apart.
            split = ((started_after or started_before) and (not started_before or started_before > today)
                     and (not started_after or started_after <= today))
            if split:
                data, begun = await asyncio.gather(
                    search, data_sources.clinical_trials(query, sponsor, status, phase, started_after, today, limit=1),
                    return_exceptions=True)
                if isinstance(data, BaseException):
                    raise data
            else:
                data, begun = await search, None
            if not data["trials"]:
                return "No trials match these filters. Try broader terms or fewer filters.", "No matching trials"
            numbers = ctx.add_sources(data["sources"])
            # Registry start dates in the future are planned, not actual, starts.
            started = lambda t: f"PLANNED start {t['start']} (not yet started)" if t["start"] and t["start"] > today else f"started {t['start']}"
            lines = [f"[{n}] {t['nct_id']} {t['title'][:100]} | {t['phase']} | {t['status']} | {t['sponsor']} | {started(t)} | "
                     f"primary completion {t['primary_completion']} | n={t['enrollment']} | {', '.join(t['conditions'][:2])}"
                     for n, t in zip(numbers, data["trials"])]
            order = "latest start first" if (started_after or started_before) else "most recently updated first"
            shown = (f"All {len(lines)} are listed" if data["total"] <= len(lines) else
                     f"The first {len(lines)} ({order}) are listed; {data['total'] - len(lines)} more match but are not shown")
            counts = f"{data['total']} trials match these filters"
            if isinstance(begun, dict) and begun["total"] <= data["total"]:
                counts += (f": {begun['total']} have already started (start date on or before today) and "
                           f"{data['total'] - begun['total']} are planned (future start date)")
            return (f"ClinicalTrials.gov, today {today}: {counts}. {shown}.\n"
                    + "\n".join(lines)), f"{data['total']:,} trials · showing {len(data['trials'])}"
        phase_digit = "".join(c for c in str(phase or "") if c in "1234")[:1]
        filters = [sponsor or query or "trials", f"phase {phase_digit}" if phase_digit else "",
                   f"started {started_after or '…'} to {started_before or '…'}" if (started_after or started_before) else ""]
        return await guarded("clinical_trials", "Searching ClinicalTrials.gov: " + " · ".join(f for f in filters if f)[:110], work,
                             query=query, sponsor=sponsor, status=status, phase=phase, after=started_after, before=started_before)

    async def pubmed(query: str, newest_first: bool = False, since_year: int | None = None) -> str:
        async def work():
            data = await data_sources.pubmed(query, limit=5, newest_first=newest_first, since_year=since_year)
            if not data["articles"]:
                return "No PubMed articles match. Try broader terms.", "No articles"
            numbers = ctx.add_sources(data["sources"])
            # Abstracts lead with conclusions and results. Report only what they state; never fill in figures.
            lines = [f"[{n}] {a['title']}. {a['authors']}. {a['journal']}, {a['date']}. {' / '.join(a['types'])}\n{a['abstract'][:900]}"
                     for n, a in zip(numbers, data["articles"])]
            return (f"PubMed: {data['total']:,} matching articles; the top {len(lines)} with abstract excerpts. Quote figures "
                    "only as they appear here.\n\n" + "\n\n".join(lines)), f"{data['total']:,} articles"
        since = f" since {since_year}" if since_year else ""
        return await guarded("pubmed", f"Searching PubMed for “{query[:60]}”{since}", work, query=query.strip().lower(),
                             newest=newest_first, since=since_year)

    async def arxiv(query: str, newest_first: bool = False) -> str:
        async def work():
            data = await data_sources.arxiv(query, newest_first=newest_first)
            if not data["papers"]:
                return "No arXiv papers match. Try broader terms.", "No papers"
            numbers = ctx.add_sources(data["sources"])
            lines = [f"[{n}] {p['title']}. {p['authors']}. {p['published']}\n{p['summary'][:600]}" for n, p in zip(numbers, data["papers"])]
            return "arXiv preprints (not peer reviewed):\n\n" + "\n\n".join(lines), f"{len(data['papers'])} papers"
        return await guarded("arxiv", f"Searching arXiv for “{query[:60]}”", work, query=query.strip().lower(), newest=newest_first)

    async def fda_approvals(drug: str | None = None, approved_since: str | None = None) -> str:
        async def work():
            data = await data_sources.fda_approvals(drug, approved_since)
            if not data["applications"]:
                return data.get("note") or "No FDA applications found.", "No applications"
            numbers = ctx.add_sources(data["sources"])
            lines = [f"[{n}] {a['brand'] or a['generic']} ({a['application']}), {a['sponsor']}. Ingredients: {a['ingredients']}. "
                     f"Original approval: {a['original_approval'] or 'n/a'}. Recent approvals: {'; '.join(a['recent_approvals'])}"
                     for n, a in zip(numbers, data["applications"])]
            note = f"\nNote: {data['lag_note']} Do not claim this list is complete." if data.get("lag_note") and not drug else ""
            return "Drugs@FDA:\n" + "\n".join(lines) + note, f"{len(data['applications'])} application{'s' if len(data['applications']) != 1 else ''}"
        label = f"Checking Drugs@FDA for {drug[:40]}" if drug else "Checking recent FDA approvals"
        return await guarded("fda_approvals", label, work, drug=drug, since=approved_since)

    # Travel ────────────────────────────────────────────────────────────────────────────────────────
    async def weather(location: str) -> str:
        async def work():
            from src.tools.base_tool import ToolContext
            from src.tools.data.weather_tool import WeatherTool
            result = await WeatherTool().execute(ToolContext(query=f"weather in {location[:80]}"))
            if not result.success:
                raise DataSourceError(result.error or "No forecast is available.")
            source = result.sources[0] if result.sources else {"title": f"Weather in {location}", "url": "https://openweathermap.org",
                                                               "domain": "openweathermap.org", "snippet": ""}
            [number] = ctx.add_sources([source])
            summary = (result.data or {}).get("formatted_summary") or source.get("snippet", "")
            return f"{summary} {_cite([number])}", source.get("title", "")[:80]
        return await guarded("weather", f"Getting the forecast for {location[:50]}", work, location=location.strip().lower())

    # Charts ────────────────────────────────────────────────────────────────────────────────────────
    async def create_chart(dataset_ids: list[str], title: str, chart_type: str = "auto", rebase_to_100: bool = False) -> str:
        async def work():
            missing = [d for d in dataset_ids if d not in ctx.datasets]
            if not dataset_ids or missing:
                known = ", ".join(ctx.datasets) or "none yet"
                raise DataSourceError(f"Unknown dataset ids {', '.join(missing) or '(none given)'}. Fetch data first; known ids: {known}.")
            if len(ctx.charts) >= 3:
                raise DataSourceError("Three charts are enough for one answer.")
            artifact, description = build_chart([ctx.datasets[d] for d in dataset_ids], title, chart_type, rebase_to_100)
            ctx.charts.append(artifact)
            # The chart appears immediately, above the written answer.
            ctx.queue.put_nowait(_sse("token", {"content": artifact + "\n\n"}))
            return description, title[:80]
        return await guarded("create_chart", "Drawing the chart", work, ids=dataset_ids, title=title, type=chart_type,
                             rebase=rebase_to_100)

    available = {
        "web_search": (web_search, SearchArgs, "Search the web for current facts, news and official pages. Trusted sites for this Space are checked first."),
        "read_webpage": (read_webpage, UrlArgs, "Read the full text of one web page, e.g. a decision, label or press release found by web_search."),
        "search_space_files": (search_space_files, FilesArgs, "Search the documents uploaded to this Space and return matching passages."),
        "calculator": (calculator, CalcArgs, "Evaluate an arithmetic expression exactly. Use for percentages, growth rates and totals."),
        "stock_prices": (stock_prices, StockArgs, "Historical daily or weekly closing prices for a stock, ETF or index, with summary statistics. Returns a dataset id for create_chart."),
        "exchange_rates": (exchange_rates, FxArgs, "European Central Bank reference exchange rates: today's rates, or a daily history between dates (returns dataset ids for create_chart)."),
        "economic_data": (economic_data, EconomyArgs, "Annual economic indicators by country from the IMF World Economic Outlook (with IMF projections) and the World Bank: GDP, growth, GDP per capita, inflation, unemployment, population, government debt, current account, health spending, life expectancy, exports. Returns dataset ids for create_chart."),
        "clinical_trials": (clinical_trials, TrialsArgs, "Search ClinicalTrials.gov for registered trials by condition, drug or sponsor, with phase, status, dates and enrollment. "
                            f"Date filters are inclusive; today is {date.today().isoformat()}, so trials started this year are "
                            f"started_after={date.today().year}-01-01 with started_before={date.today().isoformat()}."),
        "pubmed": (pubmed, PubmedArgs,"Search PubMed for biomedical and health research articles, with journal, date and abstract."),
        "arxiv": (arxiv, LiteratureArgs, "Search arXiv for preprints in computer science, physics, mathematics, statistics and quantitative biology or finance."),
        "fda_approvals": (fda_approvals, FdaArgs, "Drugs@FDA: a drug's application, sponsor and approval history, or new NDA/BLA approvals since a date."),
        "weather": (weather, WeatherArgs, "Current weather and the next 24 hours of forecast for a city."),
        "create_chart": (create_chart, ChartArgs, "Draw a chart from dataset ids returned by data tools. The chart is shown to the user automatically."),
    }
    return [StructuredTool.from_function(coroutine=available[name][0], name=name, description=available[name][2],
                                         args_schema=available[name][1]) for name in allowed if name in available]
