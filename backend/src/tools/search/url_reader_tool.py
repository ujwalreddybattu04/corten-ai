"""
URL Reader Tool — extracts and summarizes content from any webpage.

When a user pastes a URL or asks about a specific article,
this tool fetches the full page content for the LLM to work with.
"""

import re
import logging
from typing import Dict, Any

from src.tools.base_tool import BaseTool, ToolCategory, ToolContext, ToolResult, ToolStatus
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Regex to detect URLs in queries
_URL_PATTERN = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)


class URLReaderTool(BaseTool):
    name = "url_reader"
    description = "Extract and read the full content of a webpage URL for summarization or analysis"
    category = ToolCategory.SEARCH
    version = "1.0.0"

    timeout_seconds = 10.0
    max_retries = 1
    retry_delay_seconds = 0.5
    is_concurrent_safe = True
    priority = 85  # High — if user gives a URL, this is critical

    def can_handle(self, context: ToolContext) -> bool:
        """Only activate when the query contains a URL."""
        return bool(_URL_PATTERN.search(context.query))

    async def execute(self, context: ToolContext) -> ToolResult:
        from src.services.web_search_service import tavily_search_service

        if not tavily_search_service.client:
            return ToolResult(
                success=False,
                error="Tavily API key not configured (needed for extraction)",
                tool_name=self.name,
            )

        # Extract the first URL from the query
        urls = _URL_PATTERN.findall(context.query)
        if not urls:
            return ToolResult(success=False, error="No URL found in query", tool_name=self.name)

        target_url = urls[0]

        try:
            content = await tavily_search_service.extract(target_url)

            if not content:
                return ToolResult(
                    success=True,
                    data={"url": target_url, "content": "", "extracted": False},
                    sources=[{
                        "url": target_url,
                        "title": target_url,
                        "domain": self._extract_domain(target_url),
                        "favicon": f"https://www.google.com/s2/favicons?domain={self._extract_domain(target_url)}&sz=128",
                        "snippet": "Could not extract content from this URL.",
                        "citationIndex": 1,
                    }],
                    tool_name=self.name,
                    metadata={"warning": "Extraction returned empty content"},
                )

            domain = self._extract_domain(target_url)

            return ToolResult(
                success=True,
                data={
                    "url": target_url,
                    "content": content[:8000],  # Cap to avoid LLM context overflow
                    "content_length": len(content),
                    "extracted": True,
                },
                sources=[{
                    "url": target_url,
                    "title": f"Extracted: {domain}",
                    "domain": domain,
                    "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
                    "snippet": content[:300],
                    "citationIndex": 1,
                }],
                tool_name=self.name,
                cost=0.002,  # Tavily extract cost
            )

        except Exception as e:
            logger.warning(f"[URLReaderTool] Failed for {target_url}: {e}")
            raise

    async def health_check(self) -> ToolStatus:
        if not settings.TAVILY_API_KEY:
            return ToolStatus.DOWN
        return ToolStatus.HEALTHY

    def _extract_domain(self, url: str) -> str:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            return domain.replace("www.", "")
        except Exception:
            return "website"


url_reader_tool = URLReaderTool()
