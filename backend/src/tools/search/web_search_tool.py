"""
Web Search Tool — wraps Tavily search as a pluggable tool.

This is the most-used tool in the system. It handles:
  - General web search for factual, news, how-to, and opinion queries
  - Returns formatted sources ready for frontend display
  - Supports variable result counts based on query complexity
"""

import logging
import asyncio
import re
from urllib.parse import urlsplit
from typing import Dict, Any, List

from src.tools.base_tool import BaseTool, ToolCategory, ToolContext, ToolResult, ToolStatus
from src.config.settings import settings

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for current information, facts, news, and answers using Tavily"
    category = ToolCategory.SEARCH
    version = "1.0.0"

    timeout_seconds = 12.0
    max_retries = 1
    retry_delay_seconds = 0.3
    is_concurrent_safe = True
    priority = 90  # Highest priority — most queries need web search

    def can_handle(self, context: ToolContext) -> bool:
        """Web search handles almost everything except pure math and greetings."""
        skip_types = {"greeting", "identity", "math"}
        return context.query_type not in skip_types

    async def execute(self, context: ToolContext) -> ToolResult:
        from src.services.web_search_service import tavily_search_service
        from src.config.prompts import FOCUS_MODE_SEARCH_MODIFIERS

        if not tavily_search_service.client:
            return ToolResult(
                success=False,
                error="Tavily API key not configured",
                tool_name=self.name,
            )

        # Scale results by complexity
        max_results = self._results_for_complexity(context.complexity)

        # Apply focus mode search modifier to steer results
        search_query = context.query
        domains = context.metadata.get("include_domains", [])
        if domains:
            max_results = min(max_results, 3)
            # Topic modifiers (e.g. site:youtube.com) conflict with official-company evidence.
            if re.search(r"\b(located|location|headquarters?|headquartered|hq|offices?|based|registered)\b", search_query, re.I):
                page = "contact-us/"
            elif re.search(r"\b(what is|about|business|services?|doing|does)\b", search_query, re.I):
                page = "about-us/"
            else:
                page = None
        else:
            page = None
        if not domains and context.focus_mode and context.focus_mode != "all":
            modifier = FOCUS_MODE_SEARCH_MODIFIERS.get(context.focus_mode)
            if modifier:
                search_query = f"{context.query} {modifier}"

        try:
            search_options = {"max_results": max_results}
            if domains:
                search_options["include_domains"] = domains
            target_url = settings.COMPANY_WEBSITE.rstrip("/") + "/" + page if page else None
            if target_url:
                search_data, page_text = await asyncio.gather(
                    tavily_search_service.search(search_query, **search_options),
                    tavily_search_service.extract(target_url),
                )
            else:
                search_data = await tavily_search_service.search(search_query, **search_options)
                page_text = ""

            if not isinstance(search_data, dict):
                return ToolResult(success=False, error="Invalid search response", tool_name=self.name)

            results = search_data.get("results", [])[:max_results]
            if domains:
                results = [result for result in results
                           if allowed_domain(result.get("url", ""), domains)]
            if page_text and allowed_domain(target_url, domains):
                results = [{"url": target_url, "title": "Official company " + page.rstrip("/"),
                            "snippet": page_text, "domain": urlsplit(target_url).hostname}] + [
                                result for result in results if result.get("url", "") != target_url
                            ]
            results = [result for result in results if result.get("snippet", "").strip()][:max_results]
            sources = self._format_sources(results)

            return ToolResult(
                success=True,
                data={"results": results, "result_count": len(results)},
                sources=sources,
                tool_name=self.name,
                cost=0.001 * len(results),  # Rough Tavily cost estimate
            )

        except Exception as e:
            error_msg = str(e)
            if "usage limit" in error_msg.lower() or "429" in error_msg:
                return ToolResult(
                    success=False,
                    error="Web search API limit reached. Please try again later.",
                    tool_name=self.name,
                )
            raise

    async def health_check(self) -> ToolStatus:
        if not settings.TAVILY_API_KEY:
            return ToolStatus.DOWN
        return ToolStatus.HEALTHY

    def _results_for_complexity(self, complexity: int) -> int:
        """More complex queries get more search results."""
        if complexity <= 1:
            return 5
        if complexity <= 3:
            return settings.MAX_SEARCH_RESULTS
        return settings.MAX_SEARCH_RESULTS + 2

    def _format_sources(self, results: list) -> list:
        """Format raw search results for frontend display."""
        sources = []
        for idx, res in enumerate(results, start=1):
            domain = res.get("domain", "website")
            sources.append({
                "url": res.get("url", ""),
                "title": res.get("title", "Source"),
                "domain": domain,
                "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
                "snippet": res.get("snippet", ""),
                "citationIndex": idx,
            })
        return sources


web_search_tool = WebSearchTool()


def allowed_domain(url: str, domains: list[str]) -> bool:
    """Validate actual URL hosts; a provider filter alone is not an evidence boundary."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return parsed.scheme in {"http", "https"} and any(
            host == domain.lower() or host.endswith("." + domain.lower()) for domain in domains
        )
    except ValueError:
        return False
