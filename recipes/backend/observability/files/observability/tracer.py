"""`Tracer`: one per process, built by `TracingFactory`. `begin(...)` gives a `TurnTrace` per run:
its `config` goes to `ainvoke` / `astream_events`, and `finish()` returns the `TurnSummary`
(tokens, cost, duration) and logs one line.

Fail-open everywhere: a provider that cannot build a handler, or that raises on flush, costs a
warning with the error's class name (never its text: it may hold a key) and nothing else.
The core (`agentic/`) never imports this module: it only receives a `config`.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.runnables import RunnableConfig

from .models import Prices, RunInfo, TurnSummary
from .usage import UsageCollector

logger = logging.getLogger(__name__)


class Tracer(ABC):
    """Subclasses implement `_callbacks(run)` (the provider's handler) and optionally `_metadata(run)`,
    `_trace_id(run)` and `_flush()`."""

    def __init__(self, *, prices: Prices | None = None, flush_timeout: float = 2.0) -> None:
        self.prices = prices or Prices()
        self.flush_timeout = flush_timeout

    def begin(self, run: RunInfo) -> "TurnTrace":
        callbacks: list[Any] = []
        metadata: dict[str, Any] = {}
        trace_id: str | None = None
        try:
            callbacks = list(self._callbacks(run))
            metadata = dict(self._metadata(run))
            trace_id = self._trace_id(run)
        except Exception as exc:
            logger.warning("tracing disabled for this run (%s)", type(exc).__name__)
            callbacks, metadata, trace_id = [], {}, None
        return TurnTrace(run, callbacks=callbacks, metadata=metadata, trace_id=trace_id, prices=self.prices)

    def begin_turn(
        self, *, thread_id: str, tenant_id: str, user_id: str, request_id: str | None = None, tags: list[str] = ()
    ) -> "TurnTrace":
        """`begin` with keyword arguments: what an API layer that does not import this package calls."""
        return self.begin(
            RunInfo(thread_id=thread_id, tenant_id=tenant_id, user_id=user_id, request_id=request_id, tags=list(tags))
        )

    async def flush(self) -> None:
        """Push what is pending, bounded by `flush_timeout`. Call it at shutdown (lifespan)."""
        try:
            await asyncio.wait_for(asyncio.to_thread(self._flush), timeout=self.flush_timeout)
        except TimeoutError:
            logger.warning("tracing flush timed out after %.1fs", self.flush_timeout)
        except Exception as exc:
            logger.warning("tracing flush failed (%s)", type(exc).__name__)

    @abstractmethod
    def _callbacks(self, run: RunInfo) -> list[Any]: ...

    def _metadata(self, run: RunInfo) -> dict[str, Any]:
        return {}

    def _trace_id(self, run: RunInfo) -> str | None:
        return None

    def _flush(self) -> None:
        return None


class NullTracer(Tracer):
    """No provider: the run still gets the usage collector and the base metadata."""

    def _callbacks(self, run: RunInfo) -> list[Any]:
        return []


class TurnTrace:
    """One run. `config` carries the provider handler, the usage collector and the metadata."""

    def __init__(
        self,
        run: RunInfo,
        *,
        callbacks: list[Any],
        metadata: dict[str, Any],
        trace_id: str | None,
        prices: Prices,
    ) -> None:
        self.run = run
        self.trace_id = trace_id
        self.usage = UsageCollector()
        self._prices = prices
        self._started = time.monotonic()
        base_metadata = {
            "thread_id": run.thread_id,
            "tenant_id": run.tenant_id,
            "user_id": run.user_id,
            **({"request_id": run.request_id} if run.request_id else {}),
        }
        self.config: RunnableConfig = {
            "callbacks": [*callbacks, self.usage],
            "metadata": {**base_metadata, **metadata},
            "tags": list(run.tags),
            "run_name": run.name,
        }

    def finish(self, error: BaseException | None = None) -> TurnSummary:
        """Summarise and log one line. Call it in a `finally` after the run."""
        costs = [self._prices.cost_usd(u) for u in self.usage.usages]
        summary = TurnSummary(
            thread_id=self.run.thread_id,
            tenant_id=self.run.tenant_id,
            user_id=self.run.user_id,
            request_id=self.run.request_id,
            llm_calls=len(self.usage.usages),
            input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens,
            cached_input_tokens=self.usage.cached_input_tokens,
            cost_usd=None if any(c is None for c in costs) else round(sum(costs), 6),
            duration_ms=int((time.monotonic() - self._started) * 1000),
            error=type(error).__name__ if error is not None else None,
            trace_id=self.trace_id,
        )
        logger.info(
            "turn thread=%s tenant=%s llm_calls=%d tokens=%d/%d cached=%d cost_usd=%s ms=%d%s%s",
            summary.thread_id,
            summary.tenant_id,
            summary.llm_calls,
            summary.input_tokens,
            summary.output_tokens,
            summary.cached_input_tokens,
            "?" if summary.cost_usd is None else f"{summary.cost_usd:.6f}",
            summary.duration_ms,
            f" error={summary.error}" if summary.error else "",
            f" trace={summary.trace_id}" if summary.trace_id else "",
        )
        return summary
