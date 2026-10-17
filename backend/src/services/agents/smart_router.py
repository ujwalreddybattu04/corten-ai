"""
Smart Router Agent — the brain of Corten AI.

Analyzes every query to determine:
1. What TYPE of query is it (factual, comparison, news, creative, etc.)
2. How COMPLEX is it (simple lookup vs multi-step research)
3. What STRATEGY should be used (quick search, deep research, direct answer, etc.)
4. What TOOLS should be invoked (web_search, calculator, weather, etc.)

This replaces the basic 3-intent router with an intelligent classifier
that can route queries to the right pipeline for world-class answers.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from urllib.parse import urlsplit
from typing import Dict, Any, List

from src.config.settings import settings
from src.services.agents.routing_policy import direct_intent, needs_external_information
from src.services.conversation_memory import conversation_intent, answer_context
from src.services.agents.query_context import (
    clean_history, is_contextual, mentions_company, resolve_company_followup, validated_standalone,
    ambiguous_comparison_followup,
    resolve_named_followup,
)

logger = logging.getLogger(__name__)

# ── Route Strategies ──────────────────────────────────────────────────────────
# Each strategy maps to a different execution pipeline in the orchestrator.

STRATEGY_DIRECT = "direct"          # No search needed — greetings, math, identity
STRATEGY_QUICK = "quick"            # Single fast search — simple factual questions
STRATEGY_STANDARD = "standard"      # Current behavior — search + plan + answer
STRATEGY_DEEP_RESEARCH = "deep"     # Multi-step iterative research — complex queries

SMART_ROUTER_PROMPT = (
    "You are the Intelligence Router for a world-class AI search engine.\n\n"
    "Analyze the user's query and classify it for optimal handling.\n\n"
    "OUTPUT JSON with these fields:\n"
    "{{\n"
    '  "strategy": "direct" | "quick" | "standard" | "deep",\n'
    '  "complexity": 1-5,\n'
    '  "query_type": "greeting" | "identity" | "math" | "factual" | "definition" | "how_to" | "comparison" | "analysis" | "news" | "opinion" | "creative" | "code" | "multi_part",\n'
    '  "reasoning": "brief explanation",\n'
    '  "sub_questions": ["q1", "q2", ...] or []\n'
    "}}\n\n"
    "STRATEGY RULES:\n"
    '- "direct": Greetings, pure math, your own identity as {brand_name} developed by {company_name}, and tasks requiring no external facts.\n'
    '- "quick": Simple factual lookups with ONE clear answer. "What is X?", "Who is Y?", "When did Z happen?", definitions, single-entity questions.\n'
    '- "standard": Most queries — news, how-to, explanations, opinions, code help, or anything needing web sources for a solid answer.\n'
    '- "deep": ONLY for genuinely complex queries that need multi-step research: comparisons of 2+ entities, multi-faceted analysis, "best X for Y" evaluations, investment/strategy questions, queries with "compare", "vs", "pros and cons", "should I", "analyze", "in-depth", research reports, or questions that clearly have multiple angles requiring separate searches.\n\n'
    "FOCUS MODE OVERRIDES:\n"
    '- If focus_mode is "math", classify math problems with strategy "direct" (use calculator tool).\n'
    '- If focus_mode is "writing", strategy should be "direct" for writing tasks (no web search needed) or "standard" if research is needed for the writing.\n'
    '- If focus_mode is "academic", prefer "standard" or "deep" strategies to ensure thorough sourcing.\n'
    '- For all other focus modes, route normally but note the mode in your reasoning.\n\n'
    "COMPLEXITY GUIDE:\n"
    "1 = Trivial (greeting, identity, simple math)\n"
    "2 = Simple lookup (single fact, definition, who/what/when)\n"
    "3 = Moderate (explanation, how-to, current news, code snippet)\n"
    "4 = Complex (comparison, multi-angle analysis, evaluation)\n"
    "5 = Deep research (investment analysis, multi-entity comparison, strategy, comprehensive report)\n\n"
    "SUB-QUESTIONS RULES:\n"
    '- For "deep" strategy: Break the query into 2-4 specific sub-questions that each need separate research.\n'
    '- For other strategies: Return empty array [].\n'
    "- Sub-questions should be concrete, searchable queries — not vague.\n"
    "- Each sub-question should cover a DIFFERENT angle/aspect of the main query.\n\n"
    "EXAMPLES:\n"
    '"Hi there" → {{"strategy":"direct","complexity":1,"query_type":"greeting","reasoning":"Social greeting","sub_questions":[]}}\n'
    '"What is photosynthesis?" → {{"strategy":"quick","complexity":2,"query_type":"definition","reasoning":"Simple scientific definition","sub_questions":[]}}\n'
    '"Latest news on AI regulation" → {{"strategy":"standard","complexity":3,"query_type":"news","reasoning":"Current events requiring fresh sources","sub_questions":[]}}\n'
    '"Compare iPhone 16 vs Samsung S25 for photography" → {{"strategy":"deep","complexity":4,"query_type":"comparison","reasoning":"Multi-entity comparison needing separate research per device","sub_questions":["iPhone 16 Pro camera specs and photography features 2025","Samsung Galaxy S25 Ultra camera specs and photography features 2025","iPhone 16 vs Samsung S25 camera comparison expert reviews"]}}\n'
    '"Should I invest in NVIDIA stock right now?" → {{"strategy":"deep","complexity":5,"query_type":"analysis","reasoning":"Investment analysis requiring financial data, analyst opinions, market context","sub_questions":["NVIDIA stock price performance and earnings 2025","NVIDIA AI chip demand and market outlook","NVIDIA stock analyst ratings and price targets 2025","NVIDIA competitors AMD Intel AI chip market share"]}}\n'
)

SMART_ROUTER_PROMPT += (
    "\nSEARCH POLICY (takes priority over examples above):\n"
    "Prefer web search for factual questions, definitions, real entities, current events, "
    "recommendations, prices, weather, medical/legal/financial facts, and uncertain requests.\n"
    "Do not search for your own identity/developer/capabilities, greetings, pure math, "
    "creative writing, translating/editing/summarizing supplied text, or self-contained code.\n"
    "Questions about {company_name}'s business, executives, news or history DO require search.\n"
    "A greeting at the start of a factual question does not make it a greeting request.\n"
    "A writing or math focus mode does not remove the need to research external facts.\n"
    "Mixed requests need search if ANY part requires fresh or external information.\n"
    "Use conversation context to resolve follow-ups. Summarizing an earlier answer needs "
    "no search; asking for updated facts does. Never infer facts from your identity.\n"
    "Include a boolean requires_search in the JSON. For false, use strategy direct. "
    "For true, use quick/standard/deep. If uncertain, use requires_search=true.\n"
    "For supplied text transformations use query_type=text.\n"
    "For a factual follow-up with pronouns, resolve the subject from the most recent turn. "
    "Include standalone_query (a complete searchable question), context_entity (the exact "
    "entity name already present in that turn), and needs_clarification (boolean). "
    "Only resolve when there is one clear referent; set needs_clarification=true for "
    "missing/ambiguous subjects or comparisons with multiple possible referents. "
    "Do not invent an entity or treat a previous assistant assertion as verified evidence. "
    "For non-follow-ups, standalone_query is the original request and context_entity is empty.\n"
    "Today is {current_date}. For latest/current requests, use current dates, not years from examples.\n"
    "Examples: 'who developed you ??' = direct/identity/false; "
    "'who developed Python?' = quick/factual/true; "
    "'write a leave email' = direct/creative/false; "
    "'write about the latest AI news' = standard/news/true; "
    "'what is Python?' = quick/definition/true.\n"
)


class SmartRouter:
    """
    Advanced query router that classifies intent, complexity, and strategy.
    Returns routing decision that the orchestrator uses to pick the right pipeline.
    """

    async def route(self, query: str, focus_mode: str = "all", messages: list = None, *, search_tuning: bool = False) -> Dict[str, Any]:
        """
        Analyze query and return routing decision.

        Args:
            query: The user's search query
            focus_mode: Active focus mode ("all", "academic", "writing", "math", etc.)

        Returns:
            {
                "strategy": "direct" | "quick" | "standard" | "deep",
                "complexity": 1-5,
                "query_type": str,
                "reasoning": str,
                "sub_questions": list[str],
                "focus_mode": str
            }
        """
        messages = clean_history(messages)
        original_query = query
        memory_intent = conversation_intent(query)
        if memory_intent:
            return self._direct_route(query, focus_mode, memory_intent)
        named_subject = False
        if search_tuning:
            from src.services.search_answer_policy import explicit_subject
            named_subject = explicit_subject(original_query)
        if not named_subject:
            query = resolve_company_followup(query, messages, settings.COMPANY_NAME, settings.BRAND_NAME)
            query = resolve_named_followup(query, messages)
        intent = direct_intent(query, settings.BRAND_NAME, bool(messages))
        if intent:
            return self._direct_route(query, focus_mode, intent)

        if ambiguous_comparison_followup(query, messages):
            return self._direct_route(query, focus_mode, "clarification")

        company_route = self._company_route(query, focus_mode)
        if company_route:
            return company_route

        contextual = is_contextual(query)
        if named_subject:
            contextual = False
        from src.services.llm_service import groq_llm_service

        if not groq_llm_service.client:
            return self._fallback(query, focus_mode, contextual)

        system_prompt = SMART_ROUTER_PROMPT.format(
            brand_name=settings.BRAND_NAME,
            company_name=settings.COMPANY_NAME,
            current_date=datetime.now().strftime("%B %d, %Y"),
        )

        # Inject focus mode context into the router's user message
        user_message = query
        if focus_mode and focus_mode != "all":
            user_message = f"[FOCUS MODE: {focus_mode.upper()}] {query}"
        if messages:
            context = [
                {"role": m.get("role", "user"), "content": str(m.get("content", ""))[:600]}
                for m in answer_context(messages, query, max_chars=3500) if isinstance(m, dict)
            ]
            user_message = f"Conversation context: {json.dumps(context)}\nCurrent request: {user_message}"

        try:
            model_options = {}
            if settings.ROUTER_MODEL.startswith("openai/gpt-oss-"):
                model_options["reasoning_effort"] = "low"
            response = await asyncio.wait_for(groq_llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                model=settings.ROUTER_MODEL,
                temperature=0.0,
                max_tokens=1536,
                response_format={"type": "json_object"},
                **model_options,
            ), timeout=8.0)

            result = json.loads(response.choices[0].message.content)
            if not isinstance(result, dict):
                raise ValueError("Router response must be a JSON object")

            if contextual:
                resolved = validated_standalone(query, result.get("standalone_query"),
                                                 result.get("context_entity"), messages)
                if result.get("needs_clarification") is True or not resolved:
                    return self._direct_route(original_query, focus_mode, "clarification")
                query = resolved
                company_route = self._company_route(query, focus_mode)
                if company_route:
                    return company_route

            # Validate and normalize
            strategy = result.get("strategy", "standard")
            if strategy not in (STRATEGY_DIRECT, STRATEGY_QUICK, STRATEGY_STANDARD, STRATEGY_DEEP_RESEARCH):
                strategy = STRATEGY_STANDARD

            complexity = result.get("complexity", 3)
            if not isinstance(complexity, (int, float)) or complexity < 1:
                complexity = 3
            complexity = min(int(complexity), 5)

            sub_questions = result.get("sub_questions", [])
            if not isinstance(sub_questions, list):
                sub_questions = []
            # Ensure sub-questions are strings and cap at 4
            sub_questions = [str(q) for q in sub_questions if q][:4]

            # Safety: deep strategy MUST have sub-questions
            if strategy == STRATEGY_DEEP_RESEARCH and len(sub_questions) < 2:
                # Downgrade to standard if router didn't provide sub-questions
                strategy = STRATEGY_STANDARD
                sub_questions = []

            query_type = result.get("query_type", "factual")
            # Identity and self-description are accepted only by the exact rules above.
            offline_types = {"math", "creative", "code", "text"}
            requires_search = result.get("requires_search", True)
            # Enforce policy independently of a potentially contradictory strategy.
            if (requires_search is False and query_type in offline_types
                    and not needs_external_information(query)
                    and not mentions_company(query, settings.COMPANY_NAME)):
                return self._direct_route(query, focus_mode, query_type)
            if strategy == STRATEGY_DIRECT:
                strategy = STRATEGY_STANDARD
            # Unknown requests and conflicting identity labels stay search-first.
            if query_type in {"identity", "greeting", "math", "text", "creative", "code"}:
                query_type = "factual"

            # ── TOOL SELECTION ────────────────────────────────────────────
            # Use the tool registry to pick the right tools for this query
            selected_tools = self._select_tools(query, query_type, complexity, strategy, focus_mode)

            route_result = {
                "strategy": strategy,
                "complexity": complexity,
                "query_type": query_type,
                "reasoning": result.get("reasoning", ""),
                "sub_questions": sub_questions,
                "tools": selected_tools,
                "focus_mode": focus_mode,
                "requires_search": True,
                "resolved_query": query,
            }

            logger.info(
                f"[SmartRouter] '{query[:60]}' -> strategy={strategy} "
                f"complexity={complexity} type={query_type} focus={focus_mode} "
                f"tools={selected_tools} subs={len(sub_questions)}"
            )
            return route_result

        except Exception as e:
            logger.error(f"[SmartRouter] Routing failed for '{query}': {e}")
            return self._fallback(query, focus_mode, contextual)

    def _company_route(self, query: str, focus_mode: str) -> Dict[str, Any] | None:
        """Basic company facts require the company's own evidence, in every focus mode."""
        if not mentions_company(query, settings.COMPANY_NAME):
            return None
        if re.search(r"\b(compare|versus|vs|competitors?|news|reviews?|best|analysis|analy[sz]e|"
                     r"research|investment|stock|market|report)\b", query, re.I):
            return None
        if not re.search(r"\b(what|who|where|about|located|location|headquarters|hq|offices?|"
                         r"based|business|services?|products?|operate|does|doing|ceo|founder)\b", query, re.I):
            return None
        domain = (urlsplit(settings.COMPANY_WEBSITE).hostname or "").removeprefix("www.")
        return {
            "strategy": STRATEGY_QUICK, "complexity": 2, "query_type": "company",
            "reasoning": "Verify company facts using official sources",
            "sub_questions": [], "tools": ["web_search"], "focus_mode": focus_mode,
            "requires_search": True, "resolved_query": query,
            "tool_metadata": {"include_domains": [domain]} if domain else {},
        }

    def _select_tools(
        self, query: str, query_type: str, complexity: int, strategy: str, focus_mode: str = "all"
    ) -> List[str]:
        """
        Use the tool registry to select which tools should handle this query.
        Returns list of tool names. Fast — no LLM call, just pattern matching.
        """
        from src.tools import tool_registry, ToolContext

        context = ToolContext(
            query=query,
            query_type=query_type,
            complexity=complexity,
            strategy=strategy,
            focus_mode=focus_mode,
        )

        selected = tool_registry.select_tools(context)
        return [t.name for t in selected]

    def _direct_route(self, query: str, focus_mode: str, query_type: str) -> Dict[str, Any]:
        # Never select search/image/URL tools for an offline request.
        tools = ["calculator"] if query_type == "math" else []
        return {
            "strategy": STRATEGY_DIRECT,
            "complexity": 1,
            "query_type": query_type,
            "reasoning": "This request can be answered without external information",
            "sub_questions": [],
            "tools": tools,
            "focus_mode": focus_mode,
            "requires_search": False,
            "resolved_query": query,
        }

    def _fallback(self, query: str, focus_mode: str = "all", contextual: bool = False) -> Dict[str, Any]:
        """Retain offline rules on failure; prefer research for everything else."""
        intent = direct_intent(query, settings.BRAND_NAME)
        if intent:
            return self._direct_route(query, focus_mode, intent)
        if contextual:
            return self._direct_route(query, focus_mode, "clarification")
        tools = self._select_tools(query, "factual", 3, STRATEGY_STANDARD, focus_mode)
        return {
            "strategy": STRATEGY_STANDARD,
            "complexity": 3,
            "query_type": "factual",
            "reasoning": "Fallback due to routing error",
            "sub_questions": [],
            "tools": tools,
            "focus_mode": focus_mode,
            "requires_search": True,
            "resolved_query": query,
        }


smart_router = SmartRouter()
