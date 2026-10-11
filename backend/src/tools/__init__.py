"""
Corten AI Tool System — pluggable, parallel, production-grade.

Auto-registers all tools on import. The tool registry becomes the
single source of truth for what capabilities the system has.

Usage:
    from src.tools import tool_registry, tool_executor

    # Select tools for a query
    tools = tool_registry.select_tools(context)

    # Execute them in parallel
    results = await tool_executor.execute_tools(tools, context)
"""

import logging

from src.tools.base_tool import (
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolResult,
    ToolStatus,
)
from src.tools.tool_registry import tool_registry
from src.tools.tool_executor import tool_executor

logger = logging.getLogger(__name__)


def _register_all_tools() -> None:
    """
    Import and register every built-in tool.
    Called once on module load.
    """
    # ── Search Tools ──────────────────────────────────────────────────────
    from src.tools.search.web_search_tool import web_search_tool
    tool_registry.register(web_search_tool)

    from src.tools.search.url_reader_tool import url_reader_tool
    tool_registry.register(url_reader_tool)

    # ── Media Tools ───────────────────────────────────────────────────────
    from src.tools.media.image_search_tool import image_search_tool
    tool_registry.register(image_search_tool)

    # ── Compute Tools ─────────────────────────────────────────────────────
    from src.tools.compute.calculator_tool import calculator_tool
    tool_registry.register(calculator_tool)

    # ── Data Tools ────────────────────────────────────────────────────────
    from src.tools.data.weather_tool import weather_tool
    tool_registry.register(weather_tool)

    logger.info(
        f"[Tools] Registered {tool_registry.tool_count} tools: "
        f"{', '.join(tool_registry.get_tool_names())}"
    )


# Auto-register on import
_register_all_tools()

__all__ = [
    "BaseTool",
    "ToolCategory",
    "ToolContext",
    "ToolResult",
    "ToolStatus",
    "tool_registry",
    "tool_executor",
]
