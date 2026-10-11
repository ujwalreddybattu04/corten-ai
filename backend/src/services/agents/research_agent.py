"""
Research Agent — Corten AI's deep research engine.

This is the core competitive advantage. While basic AI search does ONE search
and generates an answer, the Research Agent:

1. PLANS: Breaks complex queries into sub-questions
2. SEARCHES: Executes multiple targeted searches in parallel
3. EVALUATES: Reads results and identifies gaps or conflicts
4. ITERATES: If gaps found, generates follow-up searches (up to 3 rounds)
5. SYNTHESIZES: Combines all findings into a comprehensive, cited answer

This is what Perplexity Pro and ChatGPT Deep Research do —
autonomous multi-step research with the AI deciding what to search next.

Architecture:
- Streams SSE events to frontend showing live research progress
- Each research step is visible to user (thinking, searching, reading, etc.)
- Uses parallel search for speed — all sub-queries fire simultaneously
- Caps at MAX_ITERATIONS to control cost and latency
- Final synthesis uses ALL gathered sources for comprehensive answer
"""

import json
import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, Any, List

from src.config.settings import settings

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_ITERATIONS = 3          # Maximum research rounds (search → evaluate → search again)
MAX_SOURCES_PER_SEARCH = 6  # Sources per individual search query
MAX_TOTAL_SOURCES = 15      # Cap total sources to keep LLM context manageable
EVALUATION_TIMEOUT = 3.0    # Seconds to wait for gap evaluation

# ── Prompts ───────────────────────────────────────────────────────────────────

RESEARCH_PLAN_PROMPT = (
    "You are a Research Strategist for a world-class AI search engine.\n\n"
    "The user has asked a complex question that requires multi-step research.\n"
    "Break it down into 2-4 specific, searchable sub-questions.\n\n"
    "RULES:\n"
    "- Each sub-question should target a DIFFERENT angle/aspect.\n"
    "- Sub-questions must be specific enough to get good search results.\n"
    "- Include the most important/central question first.\n"
    "- Think like an expert researcher — what would YOU search for?\n\n"
    "Output JSON:\n"
    "{{\n"
    '  "plan": "One-line research strategy description",\n'
    '  "sub_questions": ["specific search query 1", "specific search query 2", ...],\n'
    '  "key_aspects": ["aspect this research needs to cover 1", "aspect 2", ...]\n'
    "}}"
)

GAP_EVALUATION_PROMPT = (
    "You are a Research Quality Evaluator. Given a user's original question and the sources "
    "gathered so far, determine if more research is needed.\n\n"
    "ORIGINAL QUESTION: {query}\n\n"
    "RESEARCH GATHERED SO FAR:\n{gathered_summary}\n\n"
    "KEY ASPECTS TO COVER: {key_aspects}\n\n"
    "Evaluate:\n"
    "1. Are all key aspects of the question covered?\n"
    "2. Are there conflicting claims that need resolution?\n"
    "3. Is critical data missing (numbers, dates, names)?\n\n"
    "Output JSON:\n"
    "{{\n"
    '  "sufficient": true/false,\n'
    '  "confidence": 1-10,\n'
    '  "gaps": ["specific gap 1", "specific gap 2"] or [],\n'
    '  "follow_up_searches": ["precise follow-up search query 1", ...] or []\n'
    "}}\n\n"
    "RULES:\n"
    "- Set sufficient=true if confidence >= 7 and no critical gaps.\n"
    "- Follow-up searches should be DIFFERENT from what was already searched.\n"
    "- Maximum 2 follow-up searches.\n"
    "- Be efficient — don't request more searches unless genuinely needed."
)

DEEP_SYNTHESIS_PROMPT = (
    "You are a world-class research analyst for {brand_name} by {company_name}.\n"
    "The current date is {current_date}.\n\n"
    "You have conducted multi-step research on the user's question. Below are ALL the sources "
    "gathered across multiple research rounds. Your job is to synthesize them into a "
    "comprehensive, authoritative answer.\n\n"
    "WRITING RULES:\n"
    "1. DIRECT START: Lead with the key finding or direct answer. No preamble.\n"
    "2. COMPREHENSIVE: Cover ALL angles discovered during research. This is a deep analysis, not a quick answer.\n"
    "3. STRUCTURED: Use ## headers for major sections. Use tables for comparisons. Use bullet lists for data points.\n"
    "4. CITATIONS: Every factual claim MUST have [1], [2] etc. citations. Map to source numbers.\n"
    "5. NUANCED: If sources conflict, present both sides. If data is uncertain, say so.\n"
    "6. CONCLUSION: End with a clear takeaway, recommendation, or forward-looking insight.\n"
    "7. NO BIBLIOGRAPHY: NEVER list sources at the end. Our UI handles that.\n\n"
    "CONTEXT — ALL RESEARCH SOURCES:\n"
)


class ResearchAgent:
    """
    Autonomous multi-step research agent.
    Iteratively searches, evaluates, and synthesizes until the answer is comprehensive.
    Streams progress events to the frontend in real-time.
    """

    async def run(
        self,
        query: str,
        sub_questions: List[str],
        messages: list = None,
        focus_mode: str = "all",
    ) -> AsyncGenerator[str, None]:
        """
        Execute deep research pipeline. Yields SSE-formatted events.

        Events emitted:
        - research_start: {rounds: int, sub_questions: [...]}
        - research_step: {step: str, detail: str}
        - sources: {sources: [...], items: [...]}
        - research_progress: {round: int, total_sources: int, status: str}
        - token: {content: str}  (final synthesis stream)
        - related: {questions: [...]}
        - images: {images: [...]}
        - done: {}
        """
        from src.services.web_search_service import tavily_search_service
        from src.services.llm_service import groq_llm_service
        from src.services.serper_image_service import serper_image_service
        from src.config.prompts import FOCUS_MODE_SEARCH_MODIFIERS

        start_time = time.time()

        all_sources: List[Dict[str, Any]] = []
        all_urls: set = set()  # Dedup across rounds
        search_history: List[str] = []  # Track what we've already searched

        try:
            # ── PHASE 1: RESEARCH PLAN ─────────────────────────────────────
            yield self._event("research_start", {
                "max_rounds": MAX_ITERATIONS,
                "sub_questions": sub_questions,
            })

            # Generate detailed plan if sub_questions weren't provided by router
            if not sub_questions or len(sub_questions) < 2:
                yield self._event("research_step", {
                    "step": "Planning",
                    "detail": "Identifying key angles to research",
                })
                plan = await self._generate_plan(groq_llm_service, query)
                sub_questions = plan.get("sub_questions", [query])
                key_aspects = plan.get("key_aspects", [])
            else:
                key_aspects = []

            # Fire image search in background (won't block research)
            image_task = asyncio.create_task(
                serper_image_service.search_images(query, num=20)
            )
            # Fire follow-up generation in background
            follow_up_task = None  # Will be created after we have sources

            # ── PHASE 2: ITERATIVE RESEARCH LOOP ──────────────────────────
            for iteration in range(MAX_ITERATIONS):
                round_num = iteration + 1
                queries_to_search = sub_questions if iteration == 0 else sub_questions

                _progress_labels = {
                    1: "Exploring initial sources",
                    2: "Deepening the analysis",
                    3: "Verifying final details",
                }
                yield self._event("research_progress", {
                    "round": round_num,
                    "max_rounds": MAX_ITERATIONS,
                    "total_sources": len(all_sources),
                    "status": _progress_labels.get(round_num, "Continuing research"),
                })

                # ── SEARCH: Execute all sub-queries in parallel ───────────
                for sq in queries_to_search:
                    yield self._event("research_step", {
                        "step": "Searching",
                        "detail": sq,
                    })

                # Apply focus mode search modifier to steer results
                search_modifier = FOCUS_MODE_SEARCH_MODIFIERS.get(focus_mode, "") if focus_mode != "all" else ""
                search_tasks = [
                    tavily_search_service.search(
                        f"{sq} {search_modifier}".strip() if search_modifier else sq,
                        max_results=MAX_SOURCES_PER_SEARCH,
                    )
                    for sq in queries_to_search
                    if sq not in search_history
                ]
                search_history.extend(queries_to_search)

                if not search_tasks:
                    break

                results = await asyncio.gather(*search_tasks, return_exceptions=True)

                # ── COLLECT: Merge and deduplicate results ─────────────────
                new_sources_count = 0
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"[ResearchAgent] Search failed: {result}")
                        continue
                    if not isinstance(result, dict):
                        continue

                    for item in result.get("results", []):
                        url = item.get("url", "")
                        if url in all_urls:
                            continue
                        all_urls.add(url)
                        all_sources.append(item)
                        new_sources_count += 1

                        if len(all_sources) >= MAX_TOTAL_SOURCES:
                            break
                    if len(all_sources) >= MAX_TOTAL_SOURCES:
                        break

                yield self._event("research_step", {
                    "step": "Reading",
                    "detail": f"Reviewing {new_sources_count} new sources — {len(all_sources)} total gathered",
                })

                # Yield sources to frontend incrementally
                frontend_sources = self._format_sources(all_sources)
                yield self._event("sources", {
                    "sources": frontend_sources,
                    "items": frontend_sources,
                })

                # Start follow-up generation as soon as we have sources
                if follow_up_task is None and all_sources:
                    follow_up_task = asyncio.create_task(
                        groq_llm_service.generate_follow_up_questions(query, all_sources)
                    )

                # ── EVALUATE: Check if we have enough ──────────────────────
                if round_num >= MAX_ITERATIONS or len(all_sources) >= MAX_TOTAL_SOURCES:
                    yield self._event("research_step", {
                        "step": "Complete",
                        "detail": f"Collected {len(all_sources)} high-quality sources",
                    })
                    break

                # Ask LLM if research is sufficient or needs more
                evaluation = await self._evaluate_gaps(
                    groq_llm_service, query, all_sources, key_aspects
                )

                if evaluation.get("sufficient", True) or evaluation.get("confidence", 10) >= 7:
                    yield self._event("research_step", {
                        "step": "Complete",
                        "detail": "All key aspects covered",
                    })
                    break

                # ── ITERATE: Generate follow-up searches for gaps ──────────
                follow_ups = evaluation.get("follow_up_searches", [])
                if not follow_ups:
                    break

                gaps = evaluation.get("gaps", [])
                yield self._event("research_step", {
                    "step": "Refining",
                    "detail": "; ".join(gaps[:2]) if gaps else "Gathering additional perspectives",
                })

                # Next iteration will search these follow-up queries
                sub_questions = follow_ups[:2]

            # ── PHASE 3: SYNTHESIS ─────────────────────────────────────────
            thought_time = time.time() - start_time
            yield self._event("thought_time", {"time": round(thought_time, 1)})
            yield self._event("research_step", {
                "step": "Writing",
                "detail": f"Synthesizing insights from {len(all_sources)} sources",
            })

            # Stream the final synthesis
            import re
            buffer = ""
            cutoff_pattern = re.compile(
                r'(?:\n+|^)\s*(?:(?:\*\*|### |# )?(?:Sources|References|Bibliography)(?:\*\*|:)?|'
                r'(?:\[[^\]]+\]\(https?://[^\s\)]+\)\s*){2,})',
                re.IGNORECASE,
            )

            async for chunk in self._stream_synthesis(
                groq_llm_service, query, all_sources, messages, focus_mode
            ):
                buffer += chunk
                search_window = buffer[-150:] if len(buffer) > 150 else buffer
                if cutoff_pattern.search(search_window):
                    break
                yield self._event("token", {"content": chunk})

            # ── PHASE 4: DELIVER CONCURRENT RESULTS ────────────────────────
            if follow_up_task:
                try:
                    related = await follow_up_task
                    if related:
                        yield self._event("related", {"questions": related})
                except Exception as e:
                    logger.warning(f"[ResearchAgent] Follow-ups failed: {e}")

            try:
                images = await image_task
                if images:
                    yield self._event("images", {"images": images})
            except Exception as e:
                logger.warning(f"[ResearchAgent] Images failed: {e}")

            yield self._event("done", {})

        except Exception as e:
            logger.exception(f"[ResearchAgent] Research failed: {e}")
            error_msg = str(e)
            if "Tavily" in error_msg or "usage limit" in error_msg.lower():
                error_msg = "Web search limit reached. Please check your search provider plan."
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                error_msg = "API rate limit reached. Please wait a moment."
            yield self._event("error", {"message": error_msg})
            yield self._event("done", {})

    # ── Internal Methods ──────────────────────────────────────────────────────

    async def _generate_plan(self, llm_service, query: str) -> Dict[str, Any]:
        """Generate a structured research plan from the query."""
        try:
            response = await llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": RESEARCH_PLAN_PROMPT},
                    {"role": "user", "content": query},
                ],
                model=settings.ROUTER_MODEL,
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[ResearchAgent] Plan generation failed: {e}")
            return {"sub_questions": [query], "key_aspects": [], "plan": "Direct search"}

    async def _evaluate_gaps(
        self,
        llm_service,
        query: str,
        sources: List[Dict[str, Any]],
        key_aspects: List[str],
    ) -> Dict[str, Any]:
        """Evaluate if gathered sources are sufficient or have gaps."""
        # Build a compact summary of what we've gathered
        gathered_lines = []
        for i, src in enumerate(sources[:10], 1):
            title = src.get("title", "")
            snippet = src.get("snippet", "")[:200]
            gathered_lines.append(f"[{i}] {title}: {snippet}")
        gathered_summary = "\n".join(gathered_lines)

        prompt = GAP_EVALUATION_PROMPT.format(
            query=query,
            gathered_summary=gathered_summary,
            key_aspects=", ".join(key_aspects) if key_aspects else "Not specified",
        )

        try:
            response = await asyncio.wait_for(
                llm_service.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": "Evaluate the research quality."},
                    ],
                    model=settings.ROUTER_MODEL,
                    temperature=0.1,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                ),
                timeout=EVALUATION_TIMEOUT,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.warning(f"[ResearchAgent] Gap evaluation failed/timed out: {e}")
            # If evaluation fails, assume sufficient to avoid infinite loops
            return {"sufficient": True, "confidence": 7, "gaps": [], "follow_up_searches": []}

    async def _stream_synthesis(
        self,
        llm_service,
        query: str,
        sources: List[Dict[str, Any]],
        messages: list = None,
        focus_mode: str = "all",
    ) -> AsyncGenerator[str, None]:
        """Stream the final comprehensive answer using all gathered sources."""
        from datetime import datetime
        from src.config.prompts import FOCUS_MODE_PROMPTS

        current_date = datetime.now().strftime("%B %d, %Y")
        system_prompt = DEEP_SYNTHESIS_PROMPT.format(
            brand_name=settings.BRAND_NAME,
            company_name=settings.COMPANY_NAME,
            current_date=current_date,
        )

        # Inject focus mode instructions for synthesis
        if focus_mode and focus_mode != "all":
            focus_instructions = FOCUS_MODE_PROMPTS.get(focus_mode, "")
            if focus_instructions:
                system_prompt += focus_instructions

        # Add all sources to context
        for idx, src in enumerate(sources[:MAX_TOTAL_SOURCES], 1):
            snippet = src.get("snippet", "")[:800]
            system_prompt += f"Source [{idx}]:\n"
            system_prompt += f"Title: {src.get('title', 'N/A')}\n"
            system_prompt += f"Content: {snippet}\n\n"

        # Build messages
        messages_payload = [{"role": "system", "content": system_prompt}]
        if messages:
            messages_payload.extend(messages[-4:])
        messages_payload.append({"role": "user", "content": query})

        try:
            stream = await llm_service.client.chat.completions.create(
                messages=messages_payload,
                model=settings.DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=8192,
                stream=True,
                stop=["\n\n**Sources", "\n\nSources", "\n[", "\n- ["],
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.exception(f"[ResearchAgent] Synthesis streaming failed: {e}")
            raise

    def _format_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format sources for frontend display."""
        formatted = []
        for idx, src in enumerate(sources, 1):
            domain = src.get("domain", "website")
            formatted.append({
                "url": src.get("url", ""),
                "title": src.get("title", "Source"),
                "domain": domain,
                "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
                "snippet": src.get("snippet", ""),
                "citationIndex": idx,
            })
        return formatted

    def _event(self, event_type: str, data: dict) -> str:
        """Format an SSE event string."""
        return f"data: {json.dumps({'type': event_type, **data})}\n\n"


research_agent = ResearchAgent()
