"""Space agents: a LangChain agent per Space, equipped by its template.

The agent plans, calls the Space's tools one at a time (market data, trials, literature, approvals, files, web,
charts), and writes a cited answer. Steps stream to the user as they happen. Calls are bounded (model calls, tool
calls, wall time) so a confused run cannot loop or exhaust the shared provider quota.
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from src.config.settings import settings
from src.services.agents import space_templates
from src.services.agents.chat_model import CortenChatModel
from src.services.agents.toolkit import RunContext, auto_chart, build_tools
from src.services.conversation_memory import answer_context
from src.services.llm_runtime import LLMQuotaError, LLMProviderError, llm_error_details

logger = logging.getLogger(__name__)
MAX_MODEL_CALLS = 6
MAX_TOOL_CALLS = 6
RUN_TIMEOUT = 150
PREAMBLE_CHARS = 180
HEARTBEAT_SECONDS = 15
DONE = object()

WORKING_RULES = """
HOW TO WORK
- Decide what the user needs, then use the fewest tool calls that get real data, one at a time. Most questions need one or two.
  When a tool lists part of a longer result, report what it listed together with the total it gave; do not page through
  the rest or repeat a search with narrower filters or other wording.
- Never invent figures, prices, dates, trial results or approvals. Use only numbers that appear in tool results, and say plainly
  when a tool could not provide something, with what would help instead.
- Do not explain why something happened (earnings, launches, news, policy, market sentiment) unless a tool result says so.
  When the reason matters to the question, search for it and cite what you find; otherwise offer to look it up.
- Interpret only what follows from the figures: direction and size of a change, where the latest value sits between the
  period's high and low, how series compare. No price targets, support or resistance levels, trading signals, forecasts or
  statistical claims (volatility, correlation, significance) that you did not compute.
- For prices, rates or economic series: fetch them with the data tool, then call create_chart with the dataset ids it returned.
  The chart is shown above your answer automatically, so never write chart code, scripts or tables that repeat the series.
- Cite tool results with their [n] numbers immediately after the claims they support. Name sources by what they are
  (Yahoo Finance, PubMed, ClinicalTrials.gov, Drugs@FDA, World Bank), never by tool name.
- Questions about this Space itself (its purpose, template, tools, files or instructions) are answered from the Space details
  below, without tools.
- Be exact with counts, dates and comparisons: use the totals tools report, say how many items you list, copy dates exactly,
  and check every "most", "largest" or "fastest" against the numbers before writing it. Never claim a list is complete
  unless the source says so.
- Describe data and evidence; do not give personal investment, legal or medical advice, or policy and strategy
  prescriptions the user did not ask for. Use the computed summaries and rankings tools return for comparisons.
- Write a finished answer in the user's language: open with one or two sentences that answer the question, then the key
  figures, then what they mean. Do not add a heading called "Answer" or "Summary".
"""


FINAL_NOTE = ("This answer's research budget is used up. Do not call any more tools: write the final answer now from the "
              "tool results above, and say plainly what you could not verify.")
DEGRADED_NOTE = ("Tools are unavailable for the rest of this answer. Write the answer now from the tool results above; "
                 "if they do not cover the question, say plainly which data you could not fetch. Do not estimate figures.")
CHART_WORDS = re.compile(r"\b(chart|graph|plot|visuali[sz]|diagram|trend line)", re.I)


def grounding_reminder() -> str:
    """Restated in the request itself, where models follow it most reliably. Never shown or saved."""
    today = datetime.now(timezone.utc).date()
    return (f"\n\n(Today is {today.isoformat()}, so \"this year\" means {today.year}. Work from tool results: exact numbers, "
            "dates and counts, with [n] citations. No guesses about causes, sentiment or outlook unless a cited source "
            "states them.)")


class FinalAnswer(AgentMiddleware):
    """Once the research budget is spent, the next model call must write the answer: tool calls are switched off
    for it, and series the agent fetched but never charted are charted first."""

    def __init__(self, ctx: RunContext):
        super().__init__()
        self.ctx = ctx

    async def awrap_model_call(self, request, handler):
        turn = request.messages
        for index in range(len(turn) - 1, -1, -1):
            if isinstance(turn[index], HumanMessage):
                turn = turn[index + 1:]
                break
        tool_results = sum(isinstance(m, ToolMessage) for m in turn)
        model_calls = sum(isinstance(m, AIMessage) for m in turn)
        if request.tools and (tool_results >= MAX_TOOL_CALLS or model_calls >= MAX_MODEL_CALLS - 1):
            chart = await auto_chart(self.ctx)
            note = FINAL_NOTE + (f" A chart is already shown above the answer ({chart}); do not describe how to draw one." if chart else "")
            request = request.override(tool_choice="none", messages=[*request.messages, HumanMessage(content=note)])
        try:
            return await handler(request)
        except LLMQuotaError:
            raise
        except LLMProviderError as error:
            # The provider rejected this call twice before any output (usually a malformed tool call). Rather than
            # lose the whole answer, answer once more with tools off from what has been gathered so far.
            if getattr(error, "after_output", False) or not request.tools:
                raise
            logger.warning("[SpaceAgent] Model call rejected; answering without tools")
            chart = await auto_chart(self.ctx)
            note = DEGRADED_NOTE + (f" A chart is already shown above the answer ({chart})." if chart else "")
            return await handler(request.override(tools=[], tool_choice=None,
                                                  messages=[*request.messages, HumanMessage(content=note)]))


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


FULLWIDTH_CITATION = re.compile(r"【(\d{1,2}(?:\s*[,，]\s*\d{1,2})*)(?:†[^】\n]{0,80})?】")


class CitationStyle:
    """Rewrites citations some models write as 【1】 or 【1†source】 into [1], across streamed chunks: text after an
    unclosed 【 is held back until it closes (or clearly is not a citation)."""

    def __init__(self):
        self.pending = ""

    def feed(self, text: str) -> str:
        text = self.pending + text
        self.pending = ""
        start = text.rfind("【")
        if start != -1 and "】" not in text[start:] and len(text) - start < 100 and "\n" not in text[start:]:
            text, self.pending = text[:start], text[start:]
        return self._rewrite(text)

    def flush(self) -> str:
        text, self.pending = self.pending, ""
        return self._rewrite(text)

    @staticmethod
    def _rewrite(text: str) -> str:
        return FULLWIDTH_CITATION.sub(lambda m: "".join(f"[{n}]" for n in re.split(r"\s*[,，]\s*", m.group(1))), text)


def _history(messages: list, query: str) -> list:
    """Recent conversation for the agent (earlier data charts are already reduced to their titles)."""
    return [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
            for m in answer_context(messages, query)]


def system_prompt(space, instructions_block: str, personal: str, artifact_prompt: str = "") -> str:
    template = space_templates.get(space.template)
    brief = template.brief if template else space_templates.GENERAL_BRIEF
    tools = ", ".join(space_templates.TOOL_LABELS[t] for t in space.tools) or "none (this Space uses only its own files)"
    today = datetime.now(timezone.utc).strftime("%A %d %B %Y")
    role = f"the {template.name} agent" if template else "the research agent"
    files_only = ("" if space.web_search else
                  "- Web search is off in this Space: answer facts only from its files and tools, and say so when they do "
                  "not cover the question. Do not answer from general knowledge.\n")
    return (f"You are Corten, {role} for the Space \"{space.name}\". Today is {today}.\n"
            f"{brief}\nYour tools: {tools}.\n{WORKING_RULES}{files_only}{artifact_prompt}{instructions_block}{personal}")


def agent_model(mode: str):
    """Fast mode uses the small model; every other mode the large one, with deeper reasoning for Extended thinking."""
    from src.services.llm_service import groq_llm_service
    if not groq_llm_service.client:
        raise LLMProviderError("No AI provider is configured. Please contact the administrator.")
    small = mode == "fast"
    # Each model has its own per-minute token quota, so the other one stands in when the first is exhausted.
    # Reasoning stays low outside Extended thinking: the tools precompute figures, and quota is per token.
    return CortenChatModel(runtime=groq_llm_service.client, model=settings.DEFAULT_MODEL if small else settings.HEAVY_MODEL,
                           fallback_model=settings.HEAVY_MODEL if small else settings.DEFAULT_MODEL,
                           max_tokens=settings.LLM_MAX_OUTPUT_TOKENS if small else settings.LLM_HEAVY_MAX_OUTPUT_TOKENS,
                           reasoning_effort="high" if mode == "think" else "low")


async def run_space_agent(query: str, messages: list, space, turn, *, attachments: list[dict] | None = None,
                          wants_artifact: bool = False):
    """Answer one question with the Space's agent, streaming steps, sources, charts and the answer as SSE events."""
    from src.services import artifacts
    from src.services.llm_service import space_instruction_block
    started = time.monotonic()
    queue: asyncio.Queue = asyncio.Queue()
    template = space_templates.get(space.template)
    domains = list(dict.fromkeys([*space.domains, *(template.domains if template else ())]))[:10]
    ctx = RunContext(queue=queue, space=space, domains=domains)
    try:
        model = agent_model(turn.mode)
        tools = build_tools(ctx, space.tools)
        agent = create_agent(
            model, tools,
            system_prompt=system_prompt(space, space_instruction_block(space.prompt_text()), turn.personal,
                                        artifacts.PROMPT if wants_artifact else ""),
            # FinalAnswer makes the last allowed call write the answer; the limits below are backstops.
            middleware=[FinalAnswer(ctx), ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end"),
                        ToolCallLimitMiddleware(run_limit=MAX_TOOL_CALLS, exit_behavior="continue")])
    except LLMProviderError as error:
        yield _sse("error", llm_error_details(error))
        return
    except Exception:
        # Never show internal error text to the user.
        logger.exception("[SpaceAgent] Agent setup failed")
        yield _sse("error", {"message": "The Space agent could not start. Please try again."})
        return

    user_turn = query + grounding_reminder()
    if attachments:
        numbers = ctx.add_sources(attachments)
        # Already the passages most relevant to this question, within the caller's budget: never cut further.
        user_turn += "\n\nAttached documents (cite them by number):\n" + "\n\n".join(
            f"[{n}] {a['title']}\n{a['snippet']}" for n, a in zip(numbers, attachments))
    inputs = {"messages": [*_history(messages, query), HumanMessage(content=user_turn)]}
    yield _sse("status", {"content": f"{template.name} agent is working" if template else "Space agent is working"})

    state = {"answer": "", "first_token_at": None, "failed": False}

    async def produce():
        buffers: dict[str, dict] = {}
        style = CitationStyle()

        def emit(text: str):
            if text:
                queue.put_nowait(_sse("token", {"content": text}))
                state["answer"] += text

        def flush(call):
            if call["text"] and not call["tools"]:
                emit(style.feed(call["text"]))
                call["text"], call["streaming"] = "", True

        try:
            # Middleware hooks are graph steps too; the call limits, not this ceiling, bound the run.
            async for chunk, metadata in agent.astream(inputs, stream_mode="messages", config={"recursion_limit": 100}):
                if not isinstance(chunk, AIMessageChunk) or metadata.get("langgraph_node") != "model":
                    continue
                call = buffers.setdefault(chunk.id or str(metadata.get("langgraph_step")),
                                          {"text": "", "tools": False, "streaming": False})
                if chunk.tool_call_chunks:
                    # Text written before a tool call is a plan ("Let me fetch…"), not part of the answer.
                    call["tools"], call["text"] = True, ""
                text = chunk.content if isinstance(chunk.content, str) else ""
                if not text or call["tools"]:
                    continue
                if state["first_token_at"] is None:
                    state["first_token_at"] = time.monotonic()
                    queue.put_nowait(_sse("thought_time", {"time": round(time.monotonic() - started, 1)}))
                if call["streaming"]:
                    emit(style.feed(text))
                else:
                    call["text"] += text
                    if len(call["text"]) >= PREAMBLE_CHARS or "\n\n" in call["text"]:
                        flush(call)
            for call in buffers.values():
                flush(call)
            emit(style.flush())
            if CHART_WORDS.search(query):
                await auto_chart(ctx)   # asked for a chart, fetched the data, but never drew it
        except (LLMQuotaError, LLMProviderError) as error:
            state["failed"] = True
            # Same shape as the standard answer's errors (message, code, retry time).
            queue.put_nowait(_sse("error", llm_error_details(error)))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[SpaceAgent] Run failed")
            state["failed"] = True
            queue.put_nowait(_sse("error", {"message": "The Space agent could not finish this answer. Please try again."}))
        finally:
            queue.put_nowait(DONE)

    task = asyncio.create_task(produce())
    deadline = started + RUN_TIMEOUT
    try:
        while True:
            remaining = deadline - time.monotonic()
            try:
                item = await asyncio.wait_for(queue.get(), timeout=max(0.1, min(remaining, HEARTBEAT_SECONDS)))
            except asyncio.TimeoutError:
                if time.monotonic() < deadline:
                    # Slow sources and provider cooldowns can leave the stream silent; proxies close silent
                    # streams (CloudFront after 60 s). SSE comments keep it open and are ignored by clients.
                    yield ": keepalive\n\n"
                    continue
                task.cancel()
                note = ("\n\nThis took longer than expected, so the answer stops here. Ask again for the rest."
                        if state["answer"] else "The agent took too long to answer. Please try again or narrow the question.")
                yield _sse("token", {"content": note})
                break
            if item is DONE:
                break
            yield item
        if not state["answer"].strip() and not ctx.charts and not state["failed"] and task.done() and not task.cancelled():
            yield _sse("token", {"content": "I couldn't put together an answer from the available tools. "
                                            "Try rephrasing the question or naming a specific company, drug or market."})
        yield _sse("meta", {"model": model.model, "mode": f"{template.name} agent" if template else "Space agent",
                            "tools_used": sorted(ctx.used), "steps": ctx.steps})
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
