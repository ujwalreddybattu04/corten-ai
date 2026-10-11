"""
Base Tool Interface — the contract every Corten AI tool must follow.

Every tool in the system extends BaseTool and implements:
  - execute(): The actual work (search, calculate, fetch, etc.)
  - can_handle(): Whether this tool is appropriate for the given query context
  - health_check(): Whether the tool's external dependencies are available

Design principles:
  - Tools are stateless — all state lives in the execution context
  - Tools declare their own timeout, retry policy, and concurrency safety
  - Tools return a standardized ToolResult so the orchestrator doesn't care
    which tool produced the data
  - Tools track their own cost (API calls, tokens) for budget monitoring
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    SEARCH = "search"
    MEDIA = "media"
    COMPUTE = "compute"
    DATA = "data"


class ToolStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class ToolResult:
    """Standardized output from any tool execution."""
    success: bool
    data: Any = None                       # The actual result (search results, calculation, etc.)
    sources: List[Dict[str, Any]] = field(default_factory=list)  # Formatted sources for frontend
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    cost: float = 0.0                      # Estimated API cost in USD
    tool_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)  # Tool-specific extra data


@dataclass
class ToolContext:
    """
    Execution context passed to every tool.
    Contains everything the tool needs to decide how to run.
    """
    query: str
    query_type: str = "factual"            # From Smart Router
    complexity: int = 3                     # 1-5 from Smart Router
    strategy: str = "standard"             # direct/quick/standard/deep
    focus_mode: str = "all"
    messages: List[Dict[str, str]] = field(default_factory=list)  # Conversation history
    metadata: Dict[str, Any] = field(default_factory=dict)        # Extra context


class BaseTool(ABC):
    """
    Abstract base class for all Corten AI tools.

    Every tool must define:
      - name: Unique identifier (e.g., "web_search", "calculator")
      - description: What the tool does (used by router for tool selection)
      - category: ToolCategory enum
      - execute(): The core logic
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.SEARCH
    version: str = "1.0.0"

    # ── Execution Policy ──────────────────────────────────────────────────────
    timeout_seconds: float = 10.0          # Max time before the tool is killed
    max_retries: int = 2                   # Retries on transient failure
    retry_delay_seconds: float = 0.5       # Delay between retries (exponential backoff applied)
    is_concurrent_safe: bool = True        # Can run in parallel with other tools?
    priority: int = 50                     # Higher = picked first when multiple tools match (0-100)

    # ── Runtime State (set by executor, not by tool) ──────────────────────────
    _status: ToolStatus = ToolStatus.HEALTHY
    _total_calls: int = 0
    _total_failures: int = 0
    _total_cost: float = 0.0
    _avg_latency_ms: float = 0.0

    @abstractmethod
    async def execute(self, context: ToolContext) -> ToolResult:
        """
        Run the tool and return a standardized result.

        Args:
            context: ToolContext with query, type, complexity, etc.

        Returns:
            ToolResult with success/data/sources/error/cost
        """
        ...

    def can_handle(self, context: ToolContext) -> bool:
        """
        Whether this tool should be used for the given query context.
        Override in subclasses for fine-grained control.

        Default: returns True (tool is always eligible, let priority decide).
        """
        return True

    async def health_check(self) -> ToolStatus:
        """
        Check if this tool's external dependencies are available.
        Override in subclasses that depend on external APIs.

        Default: returns HEALTHY.
        """
        return ToolStatus.HEALTHY

    # ── Lifecycle Hooks (optional overrides) ──────────────────────────────────

    async def on_before_execute(self, context: ToolContext) -> None:
        """Called right before execute(). Use for logging, setup, etc."""
        pass

    async def on_after_execute(self, context: ToolContext, result: ToolResult) -> None:
        """Called right after execute(). Use for cleanup, metrics, etc."""
        pass

    # ── Metrics (managed by ToolExecutor) ─────────────────────────────────────

    def record_call(self, success: bool, latency_ms: float, cost: float = 0.0) -> None:
        """Record metrics for this tool invocation."""
        self._total_calls += 1
        if not success:
            self._total_failures += 1
        self._total_cost += cost
        # Running average
        if self._total_calls == 1:
            self._avg_latency_ms = latency_ms
        else:
            self._avg_latency_ms = (
                self._avg_latency_ms * (self._total_calls - 1) + latency_ms
            ) / self._total_calls

    def get_metrics(self) -> Dict[str, Any]:
        """Return tool performance metrics."""
        return {
            "name": self.name,
            "status": self._status.value,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "failure_rate": (
                self._total_failures / self._total_calls
                if self._total_calls > 0 else 0.0
            ),
            "avg_latency_ms": round(self._avg_latency_ms, 1),
            "total_cost_usd": round(self._total_cost, 6),
        }

    @property
    def status(self) -> ToolStatus:
        return self._status

    @status.setter
    def status(self, value: ToolStatus) -> None:
        if self._status != value:
            logger.info(f"[Tool:{self.name}] Status changed: {self._status.value} -> {value.value}")
        self._status = value

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' category={self.category.value} priority={self.priority}>"
