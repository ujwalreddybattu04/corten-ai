"""
Tool Executor — the engine that runs tools with production-grade reliability.

Handles:
  - Parallel execution: Multiple tools fire simultaneously via asyncio
  - Timeout enforcement: Each tool has its own timeout; killed if exceeded
  - Retry with exponential backoff: Transient failures retry automatically
  - Graceful degradation: If one tool fails, others still return results
  - Cost tracking: Every execution records its API cost
  - Metrics: Latency, success rate, cost tracked per tool
  - Caching: Identical queries to same tool return cached results

Usage:
    from src.tools.tool_executor import tool_executor

    results = await tool_executor.execute_tools(tools, context)
    # Returns: List[ToolResult] — one per tool, in order
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple

from src.tools.base_tool import BaseTool, ToolContext, ToolResult, ToolStatus
from src.db.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
TOOL_CACHE_TTL = 180              # 3 minutes cache for tool results
MAX_PARALLEL_TOOLS = 6            # Don't fire more than 6 tools at once
GLOBAL_TIMEOUT = 15.0             # Hard cap even if tool declares longer


class ToolExecutor:
    """
    Executes tools with retry, timeout, parallelism, and caching.
    """

    async def execute_tools(
        self,
        tools: List[BaseTool],
        context: ToolContext,
        use_cache: bool = True,
    ) -> List[ToolResult]:
        """
        Execute multiple tools in parallel with full error handling.

        Args:
            tools: List of tools to execute
            context: Shared execution context
            use_cache: Whether to check Redis cache first

        Returns:
            List of ToolResult — one per tool, preserving order.
            Failed tools return ToolResult(success=False, error=...).
        """
        if not tools:
            return []

        # Cap parallel tools to prevent resource exhaustion
        tools = tools[:MAX_PARALLEL_TOOLS]

        # Separate concurrent-safe vs exclusive tools
        concurrent_tools = [t for t in tools if t.is_concurrent_safe]
        exclusive_tools = [t for t in tools if not t.is_concurrent_safe]

        results: List[Tuple[int, ToolResult]] = []

        # Run concurrent tools in parallel
        if concurrent_tools:
            tasks = [
                self._execute_single(tool, context, use_cache)
                for tool in concurrent_tools
            ]
            concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(concurrent_results):
                tool = concurrent_tools[i]
                if isinstance(result, Exception):
                    logger.error(f"[Executor] {tool.name} raised: {result}")
                    results.append((
                        tools.index(tool),
                        ToolResult(
                            success=False,
                            error=str(result),
                            tool_name=tool.name,
                        ),
                    ))
                else:
                    results.append((tools.index(tool), result))

        # Run exclusive tools sequentially
        for tool in exclusive_tools:
            try:
                result = await self._execute_single(tool, context, use_cache)
                results.append((tools.index(tool), result))
            except Exception as e:
                logger.error(f"[Executor] Exclusive tool {tool.name} failed: {e}")
                results.append((
                    tools.index(tool),
                    ToolResult(success=False, error=str(e), tool_name=tool.name),
                ))

        # Sort by original order
        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

    async def execute_single(
        self,
        tool: BaseTool,
        context: ToolContext,
        use_cache: bool = True,
    ) -> ToolResult:
        """Execute a single tool (public API for one-off calls)."""
        return await self._execute_single(tool, context, use_cache)

    async def _execute_single(
        self,
        tool: BaseTool,
        context: ToolContext,
        use_cache: bool = True,
    ) -> ToolResult:
        """
        Execute one tool with cache check, timeout, retry, and metrics.
        """
        # ── Cache Check ───────────────────────────────────────────────────
        cache_key = f"tool:{tool.name}:{context.query.strip().lower()}"
        if use_cache:
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.info(f"[Executor] Cache HIT: {tool.name} for '{context.query[:50]}'")
                return ToolResult(
                    success=True,
                    data=cached.get("data"),
                    sources=cached.get("sources", []),
                    tool_name=tool.name,
                    metadata={"cached": True},
                )

        # ── Execute with Retry ────────────────────────────────────────────
        last_error: Optional[str] = None
        attempts = tool.max_retries + 1  # 1 initial + N retries

        for attempt in range(1, attempts + 1):
            start_ms = time.time() * 1000

            try:
                # Lifecycle hook
                await tool.on_before_execute(context)

                # Run with timeout
                effective_timeout = min(tool.timeout_seconds, GLOBAL_TIMEOUT)
                result = await asyncio.wait_for(
                    tool.execute(context),
                    timeout=effective_timeout,
                )

                elapsed_ms = time.time() * 1000 - start_ms
                result.tool_name = tool.name
                result.execution_time_ms = elapsed_ms

                # Lifecycle hook
                await tool.on_after_execute(context, result)

                # Record metrics
                tool.record_call(
                    success=result.success,
                    latency_ms=elapsed_ms,
                    cost=result.cost,
                )

                if result.success:
                    # Cache successful results
                    if use_cache and result.data is not None:
                        try:
                            await cache_set(
                                cache_key,
                                {"data": result.data, "sources": result.sources},
                                ttl=TOOL_CACHE_TTL,
                            )
                        except Exception:
                            pass  # Cache write failure is non-critical

                    logger.info(
                        f"[Executor] {tool.name} OK in {elapsed_ms:.0f}ms "
                        f"(attempt {attempt}/{attempts})"
                    )
                    return result

                # Tool returned success=False — treat as retryable
                last_error = result.error or "Tool returned unsuccessful result"

            except asyncio.TimeoutError:
                elapsed_ms = time.time() * 1000 - start_ms
                last_error = f"Timeout after {effective_timeout}s"
                tool.record_call(success=False, latency_ms=elapsed_ms)
                logger.warning(
                    f"[Executor] {tool.name} TIMEOUT on attempt {attempt}/{attempts}"
                )

            except Exception as e:
                elapsed_ms = time.time() * 1000 - start_ms
                last_error = str(e)
                tool.record_call(success=False, latency_ms=elapsed_ms)
                logger.warning(
                    f"[Executor] {tool.name} ERROR on attempt {attempt}/{attempts}: {e}"
                )

                # Non-retryable errors: don't waste time retrying
                if self._is_fatal_error(e):
                    break

            # Exponential backoff before retry
            if attempt < attempts:
                delay = tool.retry_delay_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        # All attempts exhausted
        tool.record_call(success=False, latency_ms=0)

        # Update tool health if failing too much
        if tool._total_calls >= 5 and tool._total_failures / tool._total_calls > 0.5:
            tool.status = ToolStatus.DEGRADED
        if tool._total_calls >= 10 and tool._total_failures / tool._total_calls > 0.8:
            tool.status = ToolStatus.DOWN

        return ToolResult(
            success=False,
            error=last_error or "All retry attempts failed",
            tool_name=tool.name,
        )

    def _is_fatal_error(self, error: Exception) -> bool:
        """Determine if an error is non-retryable."""
        error_str = str(error).lower()
        fatal_signals = [
            "api key",
            "unauthorized",
            "forbidden",
            "not found",
            "invalid",
            "authentication",
            "permission denied",
        ]
        return any(signal in error_str for signal in fatal_signals)


# ── Singleton ─────────────────────────────────────────────────────────────────
tool_executor = ToolExecutor()
