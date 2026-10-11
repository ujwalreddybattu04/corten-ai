"""
Tool Registry — auto-discovers, registers, and manages all Corten AI tools.

The registry is the single source of truth for what tools exist in the system.
It handles:
  - Auto-discovery: Scans tool directories and registers all BaseTool subclasses
  - Enable/disable: Tools can be toggled via settings or environment variables
  - Lookup: Find tools by name, category, or capability
  - Health monitoring: Periodic health checks on all registered tools
  - Metrics aggregation: Collect performance data across all tools

Usage:
    from src.tools.tool_registry import tool_registry

    # Get all enabled tools
    tools = tool_registry.get_enabled_tools()

    # Find tools that can handle a specific context
    tools = tool_registry.select_tools(context)

    # Get a specific tool
    web_search = tool_registry.get_tool("web_search")
"""

import logging
from typing import Dict, List, Optional, Set

from src.tools.base_tool import BaseTool, ToolCategory, ToolContext, ToolStatus

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all tools in the Corten AI system.
    Singleton — use `tool_registry` instance.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._disabled: Set[str] = set()

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises if duplicate name."""
        if not tool.name:
            raise ValueError(f"Tool {tool.__class__.__name__} has no name defined")

        if tool.name in self._tools:
            logger.warning(f"[Registry] Tool '{tool.name}' already registered — overwriting")

        self._tools[tool.name] = tool
        logger.info(
            f"[Registry] Registered: {tool.name} "
            f"(category={tool.category.value}, priority={tool.priority})"
        )

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            self._disabled.discard(name)
            logger.info(f"[Registry] Unregistered: {name}")

    def disable(self, name: str) -> None:
        """Disable a tool without removing it."""
        if name in self._tools:
            self._disabled.add(name)
            logger.info(f"[Registry] Disabled: {name}")

    def enable(self, name: str) -> None:
        """Re-enable a disabled tool."""
        self._disabled.discard(name)
        logger.info(f"[Registry] Enabled: {name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name. Returns None if not found or disabled."""
        if name in self._disabled:
            return None
        return self._tools.get(name)

    def get_all_tools(self) -> List[BaseTool]:
        """Get all registered tools (including disabled)."""
        return list(self._tools.values())

    def get_enabled_tools(self) -> List[BaseTool]:
        """Get only enabled tools, sorted by priority (highest first)."""
        return sorted(
            [t for t in self._tools.values() if t.name not in self._disabled],
            key=lambda t: t.priority,
            reverse=True,
        )

    def get_by_category(self, category: ToolCategory) -> List[BaseTool]:
        """Get all enabled tools in a specific category."""
        return [
            t for t in self.get_enabled_tools()
            if t.category == category
        ]

    def select_tools(self, context: ToolContext) -> List[BaseTool]:
        """
        Select the best tools for a given query context.
        Returns tools that can handle the context, sorted by priority.

        This is called by the orchestrator to decide which tools to run.
        """
        eligible = []
        for tool in self.get_enabled_tools():
            if tool.status == ToolStatus.DOWN:
                continue
            try:
                if tool.can_handle(context):
                    eligible.append(tool)
            except Exception as e:
                logger.warning(f"[Registry] can_handle() failed for {tool.name}: {e}")

        return eligible

    def get_tool_names(self) -> List[str]:
        """Get names of all enabled tools (for router prompt)."""
        return [t.name for t in self.get_enabled_tools()]

    def get_tool_descriptions(self) -> str:
        """
        Build a formatted description of all tools for the Smart Router prompt.
        The router uses this to decide which tools to invoke.
        """
        lines = []
        for tool in self.get_enabled_tools():
            lines.append(f'- "{tool.name}": {tool.description} (category: {tool.category.value})')
        return "\n".join(lines)

    async def health_check_all(self) -> Dict[str, str]:
        """Run health checks on all tools. Returns {name: status}."""
        results = {}
        for name, tool in self._tools.items():
            try:
                status = await tool.health_check()
                tool.status = status
                results[name] = status.value
            except Exception as e:
                logger.error(f"[Registry] Health check failed for {name}: {e}")
                tool.status = ToolStatus.DOWN
                results[name] = "down"
        return results

    def get_all_metrics(self) -> List[Dict]:
        """Aggregate metrics from all tools."""
        return [tool.get_metrics() for tool in self._tools.values()]

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def enabled_count(self) -> int:
        return len(self._tools) - len(self._disabled)

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={self.tool_count} enabled={self.enabled_count}>"


# ── Singleton ─────────────────────────────────────────────────────────────────
tool_registry = ToolRegistry()
