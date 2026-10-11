"""
Search Orchestrator — the central nervous system of Corten AI.

Routes every query through the Smart Router, then dispatches to the right pipeline:
- DIRECT: No search, instant LLM answer (greetings, math, identity)
- QUICK: Single fast search → immediate answer (simple factual lookups)
- STANDARD: Tool execution + plan + stream answer (most queries)
- DEEP: Multi-step Research Agent (complex comparisons, analysis, strategy)

Now powered by the Tool System — tools are selected dynamically by the router
and executed in parallel by the ToolExecutor.
"""

import json
import re
import asyncio
import logging
import time
from typing import AsyncGenerator

from src.services.llm_service import groq_llm_service
from src.services.llm_runtime import LLMProviderError, llm_error_details
from src.services.agents.smart_router import smart_router, STRATEGY_DIRECT, STRATEGY_QUICK, STRATEGY_STANDARD, STRATEGY_DEEP_RESEARCH
from src.services.agents.research_agent import research_agent
from src.tools import tool_registry, tool_executor, ToolContext, ToolResult
from src.config.settings import settings
from src.services.application_facts import self_answer
from src.services.agents.query_context import clean_history
from src.services.conversation_memory import recall_answer, acknowledge_note, MISSING_HISTORY
from src.services.answer_grounding import verify_company_answer, UNVERIFIED_ANSWER, company_answer_cache_key
from src.services.company_evidence import official_office_answer
from src.db.redis import cache_get, cache_set, make_search_cache_key

logger = logging.getLogger(__name__)

_SEARCH_CACHE_TTL = 300  # 5 minutes

# Regex to detect and cut off LLM-generated source lists
_CUTOFF_PATTERN = re.compile(
    r'(?:\n+|^)\s*(?:(?:\*\*|### |# )?(?:Sources|References|Bibliography)(?:\*\*|:)?|'
    r'(?:\[[^\]]+\]\(https?://[^\s\)]+\)\s*){2,})',
    re.IGNORECASE,
)


class SearchOrchestrator:

    async def stream_search(
        self, query: str, focus_mode: str = "all", messages: list = None
    ) -> AsyncGenerator[str, None]:
        """
        Main entry point for all search queries.
        Smart Router decides the strategy + tools, orchestrator dispatches.
        """
        if not query.strip():
            yield _sse("error", {"message": "Query cannot be empty"})
            yield _sse("done", {})
            return

        background_tasks = []
        messages = clean_history(messages)
        try:
            start_time = time.time()
            logger.info("[Orchestrator] Request: query_chars=%d history_messages=%d focus=%s", len(query), len(messages), focus_mode)

            # ── PHASE 0: SMART ROUTING ────────────────────────────────────
            short_query = (query[:55] + "\u2026") if len(query) > 55 else query
            yield _sse("status", {"content": f"Understanding \"{short_query}\""})

            route = await smart_router.route(query, focus_mode, messages)
            query = route.get("resolved_query", query)
            strategy = route.get("strategy", STRATEGY_STANDARD)
            if route.get("requires_search") is False:
                strategy = STRATEGY_DIRECT
            complexity = route.get("complexity", 3)
            query_type = route.get("query_type", "factual")
            sub_questions = route.get("sub_questions", [])
            selected_tool_names = route.get("tools", [])
            if strategy == STRATEGY_DIRECT:
                selected_tool_names = [name for name in selected_tool_names if name == "calculator" and query_type == "math"]

            logger.info(
                f"[Orchestrator] Route: strategy={strategy} complexity={complexity} "
                f"type={query_type} tools={selected_tool_names} subs={len(sub_questions)}"
            )

            # Notify frontend which tools were selected
            if selected_tool_names:
                yield _sse("tools_selected", {
                    "tools": selected_tool_names,
                    "strategy": strategy,
                    "query_type": query_type,
                    "focus_mode": focus_mode,
                })

            # Emit a dynamic routing status so user sees what approach was chosen
            _STRATEGY_LABELS = {
                STRATEGY_DIRECT: "Generating a direct answer",
                STRATEGY_QUICK: "Running a quick lookup",
                STRATEGY_STANDARD: "Researching across multiple sources",
                STRATEGY_DEEP_RESEARCH: "Conducting deep multi-step research",
            }
            yield _sse("status", {"content": _STRATEGY_LABELS.get(strategy, "Processing your query")})

            # ── DISPATCH BY STRATEGY ──────────────────────────────────────

            if strategy == STRATEGY_DIRECT:
                if query_type in {"question_recall", "conversation", "conversation_note"}:
                    remembered = acknowledge_note(query) if query_type == "conversation_note" else recall_answer(query, messages)
                    if remembered is not None or (not messages and query_type != "conversation_note"):
                        yield _sse("token", {"content": remembered or MISSING_HISTORY})
                    else:
                        async for chunk in groq_llm_service.stream_answer(
                            query, [], messages, focus_mode="all", conversation_only=True
                        ):
                            yield _sse("token", {"content": chunk})
                    yield _sse("done", {})
                    return
                # ── DIRECT: Check if calculator/weather can handle it ─────
                verified_answer = self_answer(query_type)
                if verified_answer:
                    yield _sse("token", {"content": verified_answer})
                    yield _sse("done", {})
                    return
                compute_tools = [
                    tool_registry.get_tool(name)
                    for name in selected_tool_names
                    if name in ("calculator", "weather")
                ]
                compute_tools = [t for t in compute_tools if t is not None]

                if compute_tools:
                    # Run compute tools first
                    tool_context = ToolContext(
                        query=query,
                        query_type=query_type,
                        complexity=complexity,
                        strategy=strategy,
                        messages=messages or [],
                    )

                    for tool in compute_tools:
                        yield _sse("tool_executing", {
                            "tool": tool.name,
                            "description": tool.description,
                        })

                    results = await tool_executor.execute_tools(compute_tools, tool_context)

                    for result in results:
                        if result.success and result.data:
                            yield _sse("tool_result", {
                                "tool": result.tool_name,
                                "data": result.data,
                                "execution_time_ms": round(result.execution_time_ms),
                            })

                            # If tool provides formatted output, inject into LLM context
                            formatted = result.data.get("formatted", "")
                            if formatted:
                                thought_time = time.time() - start_time
                                yield _sse("thought_time", {"time": round(thought_time, 1)})

                                # Let LLM enhance the tool result with explanation
                                tool_context_str = f"TOOL RESULT ({result.tool_name}):\n{formatted}\n\nProvide a clear, helpful response incorporating this data. Be conversational. Start directly with the answer."
                                async for chunk in groq_llm_service.stream_answer(
                                    tool_context_str, [], messages, focus_mode
                                ):
                                    yield _sse("token", {"content": chunk})

                                yield _sse("done", {})
                                return

                # No compute tools or they failed — pure LLM answer
                thought_time = time.time() - start_time
                yield _sse("thought_time", {"time": round(thought_time, 1)})

                async for chunk in groq_llm_service.stream_answer(query, [], messages, focus_mode):
                    yield _sse("token", {"content": chunk})

                yield _sse("done", {})
                return

            if strategy == STRATEGY_DEEP_RESEARCH:
                # Deep research — hand off to Research Agent
                yield _sse("research_start", {
                    "strategy": "deep",
                    "complexity": complexity,
                    "sub_questions": sub_questions,
                })

                async for event in research_agent.run(
                    query=query,
                    sub_questions=sub_questions,
                    messages=messages,
                    focus_mode=focus_mode,
                ):
                    yield event

                return

            # ── QUICK & STANDARD PATHS ────────────────────────────────────
            # Now powered by the Tool System

            # Build tool context
            tool_context = ToolContext(
                query=query,
                query_type=query_type,
                complexity=complexity,
                strategy=strategy,
                focus_mode=focus_mode,
                messages=messages or [],
                metadata=route.get("tool_metadata", {}),
            )

            # Get the actual tool objects for selected tools
            selected_tools = []
            for name in selected_tool_names:
                tool = tool_registry.get_tool(name)
                if tool:
                    selected_tools.append(tool)

            # Ensure we always have web_search for quick/standard
            web_search = tool_registry.get_tool("web_search")
            if web_search and web_search not in selected_tools:
                selected_tools.insert(0, web_search)

            # Separate primary tools (search/compute/data) from supplementary (images)
            primary_tools = [t for t in selected_tools if t.name != "image_search"]
            image_tool = tool_registry.get_tool("image_search") if query_type != "company" else None

            # Routing already supplies the research intent. A second AI request
            # used only for progress text would consume quota without improving search.

            yield _sse("query_step", {"content": query})

            # Emit tool execution events
            for tool in primary_tools:
                yield _sse("tool_executing", {
                    "tool": tool.name,
                    "description": tool.description,
                })

            tool_names_display = ", ".join(t.name.replace("_", " ").title() for t in primary_tools)
            yield _sse("status", {"content": f"Searching with {tool_names_display}"})

            # ── PHASE 3: EXECUTE ALL TOOLS IN PARALLEL ────────────────────
            primary_task = asyncio.create_task(
                tool_executor.execute_tools(primary_tools, tool_context)
            )
            background_tasks.append(primary_task)

            if image_tool:
                image_task = asyncio.create_task(
                    tool_executor.execute_single(image_tool, tool_context, use_cache=False)
                )
                background_tasks.append(image_task)
            else:
                image_task = None

            # Await primary results
            tool_results = await primary_task

            # Collect all sources and tool data
            all_sources = []
            all_tool_data = {}
            search_results_for_llm = []

            for result in tool_results:
                if not result.success:
                    logger.warning(
                        f"[Orchestrator] Tool {result.tool_name} failed: {result.error}"
                    )
                    continue

                # Emit per-tool result event
                yield _sse("tool_result", {
                    "tool": result.tool_name,
                    "execution_time_ms": round(result.execution_time_ms),
                    "success": True,
                })

                # Collect sources
                if result.sources:
                    all_sources.extend(result.sources)

                # Collect tool-specific data for LLM context
                if result.data:
                    all_tool_data[result.tool_name] = result.data

                    # If it's web search, extract results for LLM
                    if result.tool_name == "web_search":
                        search_results_for_llm = result.data.get("results", [])

            # Deduplicate sources by URL
            seen_urls = set()
            unique_sources = []
            for src in all_sources:
                url = src.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    src["citationIndex"] = len(unique_sources) + 1
                    unique_sources.append(src)

            # Send sources to frontend
            if unique_sources:
                yield _sse("sources", {"sources": unique_sources, "items": unique_sources})
                yield _sse("status", {"content": f"Reviewing {len(unique_sources)} sources"})

            # ── PHASE 4: LAYER IN PLAN ────────────────────────────────────
            if strategy != STRATEGY_QUICK and route.get("reasoning"):
                yield _sse("thought", {"content": route["reasoning"]})

            # ── PHASE 5: STREAM LLM ANSWER ────────────────────────────────
            thought_time = time.time() - start_time
            yield _sse("thought_time", {"time": round(thought_time, 1)})
            src_count = len(unique_sources) if unique_sources else len(search_results_for_llm)
            yield _sse("status", {"content": f"Synthesizing answer from {src_count} sources"})

            # Build enriched context for LLM with tool results
            enriched_results = [dict(source) for source in unique_sources]
            for tool_name, data in all_tool_data.items():
                if tool_name == "web_search":
                    continue  # Already included
                formatted = data.get("formatted", "")
                if formatted or (tool_name == "url_reader" and data.get("content")):
                    tool_result = next(result for result in tool_results if result.tool_name == tool_name)
                    source_url = tool_result.sources[0].get("url") if tool_result.sources else None
                    existing = next((source for source in enriched_results if source["url"] == source_url), None)
                    if existing is not None:
                        existing["snippet"] = formatted or data["content"]
                        continue
                    enriched_results.append({
                        "title": f"[{tool_name.upper()} TOOL RESULT]",
                        "url": "",
                        "snippet": formatted or data["content"],
                        "domain": f"tool:{tool_name}",
                        "citationIndex": None,
                    })

            if not any(result.get("snippet", "").strip() for result in enriched_results):
                yield _sse("token", {"content": UNVERIFIED_ANSWER})
                yield _sse("done", {})
                return

            if query_type == "company":
                office_answer = official_office_answer(query, enriched_results, settings.COMPANY_NAME)
                if office_answer:
                    yield _sse("token", {"content": office_answer})
                    yield _sse("done", {})
                    return
                answer_cache_key = company_answer_cache_key(query, enriched_results)
                cached_answer = await cache_get(answer_cache_key)
                if isinstance(cached_answer, dict) and cached_answer.get("verified") is True and cached_answer.get("answer"):
                    yield _sse("token", {"content": cached_answer["answer"]})
                    yield _sse("done", {})
                    return

            buffer = ""
            # The subject is already resolved. Old assistant claims must not contaminate company facts.
            answer_history = [] if query_type == "company" else messages
            async for chunk in groq_llm_service.stream_answer(query, enriched_results, answer_history, focus_mode,
                                                              company_lookup=query_type == "company"):
                buffer += chunk
                search_window = buffer[-150:] if len(buffer) > 150 else buffer
                if _CUTOFF_PATTERN.search(search_window):
                    logger.info("[Orchestrator] Cutoff: source list detected, truncating")
                    break
                if query_type != "company":
                    yield _sse("token", {"content": chunk})

            if query_type == "company":
                yield _sse("status", {"content": "Checking the answer against official sources"})
                if not await verify_company_answer(query, buffer, enriched_results, groq_llm_service):
                    # One bounded repair using the same evidence. Neither rejected draft is exposed.
                    yield _sse("status", {"content": "Refining the answer using verified evidence"})
                    repair_query = (query + "\nAnswer briefly using only explicit evidence. "
                                    "Use the company brand name from the sources, not an assumed legal name. "
                                    "Do not infer headquarters. Include inline source IDs after every factual claim.")
                    buffer = "".join([chunk async for chunk in groq_llm_service.stream_answer(
                        repair_query, enriched_results, [], focus_mode, company_lookup=True)])
                    if not await verify_company_answer(query, buffer, enriched_results, groq_llm_service):
                        yield _sse("token", {"content": UNVERIFIED_ANSWER})
                        yield _sse("done", {})
                        return
                yield _sse("token", {"content": buffer})
                await cache_set(answer_cache_key, {"verified": True, "answer": buffer}, ttl=180)

            # ── PHASE 6: DELIVER CONCURRENT RESULTS ───────────────────────
            try:
                # Give the answer priority over optional suggestions on a small quota.
                related = await asyncio.wait_for(
                    groq_llm_service.generate_follow_up_questions(query, enriched_results), timeout=4
                ) if query_type != "company" else []
                if related:
                    yield _sse("related", {"questions": related})
            except Exception as e:
                logger.warning(f"[Orchestrator] Follow-ups failed: {e}")

            if image_task:
                try:
                    image_result = await image_task
                    if image_result.success and image_result.data:
                        images = image_result.data.get("images", [])
                        if images:
                            yield _sse("images", {"images": images})
                except Exception as e:
                    logger.warning(f"[Orchestrator] Images failed: {e}")

            # Emit final metrics
            total_cost = sum(r.cost for r in tool_results if r.success)
            yield _sse("meta", {
                "model": settings.DEFAULT_MODEL,
                "tools_used": [r.tool_name for r in tool_results if r.success],
                "total_tool_cost": round(total_cost, 6),
            })

            yield _sse("done", {})

        except Exception as e:
            logger.exception(f"[Orchestrator] Search failed: {e}")
            error_message = str(e)
            if "Tavily" in error_message:
                error_message = "Web search limit reached. Please check your search provider plan."
            elif "429" in error_message or "rate limit" in error_message.lower():
                error_message = "API rate limit reached. Please wait a moment."
            yield _sse("error", llm_error_details(e) if isinstance(e, LLMProviderError) else {"message": error_message})
            yield _sse("done", {})
        finally:
            for task in background_tasks:
                if not task.done():
                    task.cancel()
            if background_tasks:
                await asyncio.gather(*background_tasks, return_exceptions=True)

    async def stream_article_summary(
        self,
        title: str,
        url: str,
        description: str = "",
        followup: str = "",
        previous_summary: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Perplexity-style article summarization + follow-up handling.
        """
        from src.services.web_search_service import tavily_search_service
        from src.services.serper_image_service import serper_image_service

        if not title.strip():
            yield _sse("error", {"message": "Title cannot be empty"})
            yield _sse("done", {})
            return

        try:
            start_time = time.time()

            # ── FOLLOW-UP PATH ────────────────────────────────────────────
            if followup:
                logger.info(f"[Orchestrator] Article follow-up: '{followup}'")
                short_followup = (followup[:50] + "\u2026") if len(followup) > 50 else followup
                yield _sse("status", {"content": f"Researching: \"{short_followup}\""})
                yield _sse("query_step", {"content": followup})

                search_data = await tavily_search_service.search(
                    f"{title} {followup}", max_results=settings.MAX_SEARCH_RESULTS
                )
                search_results = []
                if isinstance(search_data, dict):
                    search_results = search_data.get("results", [])[:settings.MAX_SEARCH_RESULTS]

                yield _sse("thought", {"content": f"Found {len(search_results)} relevant sources"})
                frontend_sources = _format_sources(search_results)
                yield _sse("sources", {"sources": frontend_sources, "items": frontend_sources})

                thought_time = time.time() - start_time
                yield _sse("thought_time", {"time": round(thought_time, 1)})
                yield _sse("status", {"content": "Composing a detailed answer"})

                enriched_results = search_results.copy()
                if previous_summary:
                    enriched_results.insert(0, {
                        "title": f"Previous AI Summary of: {title}",
                        "url": url,
                        "snippet": previous_summary[:3000],
                        "domain": "previous-summary",
                    })

                async for chunk in groq_llm_service.stream_article_followup(
                    title=title,
                    followup=followup,
                    previous_summary=previous_summary,
                    search_results=enriched_results,
                ):
                    yield _sse("token", {"content": chunk})

                yield _sse("done", {})
                return

            # ── INITIAL SUMMARY PATH ──────────────────────────────────────
            logger.info(f"[Orchestrator] Article summary: '{title}'")

            # Short title for inline status messages (truncate long headlines)
            short_title = (title[:60] + "\u2026") if len(title) > 60 else title

            yield _sse("status", {"content": f"Reading \"{short_title}\""})

            extract_task = asyncio.create_task(tavily_search_service.extract(url)) if url else None
            search_task = asyncio.create_task(
                tavily_search_service.search(title, max_results=settings.MAX_SEARCH_RESULTS)
            )
            image_task = asyncio.create_task(serper_image_service.search_images(title, num=10))

            yield _sse("query_step", {"content": title})
            yield _sse("status", {"content": "Searching for additional context"})

            article_text = ""
            if extract_task:
                try:
                    article_text = await asyncio.wait_for(extract_task, timeout=8)
                    if article_text:
                        chars = len(article_text)
                        yield _sse("thought", {"content": f"Extracted {chars:,} characters from the original article"})
                except Exception as e:
                    logger.warning(f"[Orchestrator] Article extraction failed: {e}")
                    yield _sse("thought", {"content": "Original article unavailable \u2014 relying on search context"})

            search_data = await search_task
            search_results = []
            if isinstance(search_data, dict):
                search_results = search_data.get("results", [])[:settings.MAX_SEARCH_RESULTS]

            yield _sse("thought", {"content": f"Cross-referencing {len(search_results)} sources"})
            frontend_sources = _format_sources(search_results)
            yield _sse("sources", {"sources": frontend_sources, "items": frontend_sources})

            yield _sse("status", {"content": "Analyzing key claims and data"})

            thought_time = time.time() - start_time
            yield _sse("thought_time", {"time": round(thought_time, 1)})
            yield _sse("status", {"content": "Synthesizing insights into a summary"})

            enriched_results = search_results.copy()
            if article_text:
                enriched_results.insert(0, {
                    "title": title,
                    "url": url,
                    "snippet": article_text[:2000],
                    "domain": "original-article",
                })

            async for chunk in groq_llm_service.stream_article_summary(
                title=title,
                article_text=article_text,
                search_results=enriched_results,
                description=description,
            ):
                yield _sse("token", {"content": chunk})

            try:
                search_images = await image_task
                if search_images:
                    yield _sse("images", {"images": search_images})
            except Exception:
                pass

            yield _sse("done", {})

        except Exception as e:
            logger.exception(f"[Orchestrator] Article summary failed: {e}")
            error_message = str(e)
            if "Tavily" in error_message:
                error_message = "Web search limit reached."
            yield _sse("error", llm_error_details(e) if isinstance(e, LLMProviderError) else {"message": error_message})
            yield _sse("done", {})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


def _format_sources(results: list) -> list:
    """Format raw search results for frontend display."""
    sources = []
    for idx, res in enumerate(results, start=1):
        domain = res.get("domain", "website")
        sources.append({
            "url": res.get("url"),
            "title": res.get("title") or "Source",
            "domain": domain,
            "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
            "snippet": res.get("snippet") or "",
            "citationIndex": idx,
        })
    return sources


search_orchestrator = SearchOrchestrator()
