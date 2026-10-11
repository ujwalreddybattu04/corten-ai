"""
Image Search Tool — wraps Serper image search as a pluggable tool.

Fires in parallel with web search for visual queries.
Returns formatted image data for the frontend ImagesGrid component.
"""

import logging
from typing import Dict, Any, List

from src.tools.base_tool import BaseTool, ToolCategory, ToolContext, ToolResult, ToolStatus
from src.config.settings import settings

logger = logging.getLogger(__name__)


class ImageSearchTool(BaseTool):
    name = "image_search"
    description = "Search Google Images for visual content, photos, diagrams, and illustrations"
    category = ToolCategory.MEDIA
    version = "1.0.0"

    timeout_seconds = 6.0
    max_retries = 1
    retry_delay_seconds = 0.3
    is_concurrent_safe = True
    priority = 40  # Lower priority — supplementary to web search

    def can_handle(self, context: ToolContext) -> bool:
        """Image search for visual, comparison, and factual queries. Skip math/greetings."""
        skip_types = {"greeting", "identity", "math"}
        return context.query_type not in skip_types

    async def execute(self, context: ToolContext) -> ToolResult:
        from src.services.serper_image_service import serper_image_service

        if not settings.SERPER_API_KEY:
            return ToolResult(
                success=False,
                error="Serper API key not configured",
                tool_name=self.name,
            )

        # Adjust image count by query type
        num_images = 20 if context.query_type in ("comparison", "how_to") else 12

        try:
            images = await serper_image_service.search_images(
                context.query, num=num_images
            )

            return ToolResult(
                success=True,
                data={"images": images, "image_count": len(images)},
                sources=[],  # Images don't produce citation sources
                tool_name=self.name,
                cost=0.001,
            )

        except Exception as e:
            logger.warning(f"[ImageSearchTool] Failed: {e}")
            raise

    async def health_check(self) -> ToolStatus:
        if not settings.SERPER_API_KEY:
            return ToolStatus.DOWN
        return ToolStatus.HEALTHY


image_search_tool = ImageSearchTool()
