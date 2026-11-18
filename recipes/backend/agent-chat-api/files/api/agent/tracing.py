"""Per-turn tracing, optional: if `app.state.tracer` exists (recipe `observability`), every turn
runs with its `config` and ends with `finish()`; if not, the turn runs with the default config.

The tracer is duck-typed on purpose: this recipe does not import `observability`. What it needs:
`begin_turn(thread_id=, tenant_id=, user_id=, request_id=) -> trace` with `.config` and `.finish(error=None)`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import Request
from langchain_core.runnables import RunnableConfig

from ..request_id import current_request_id
from agentic.memory import MemoryKey


def get_tracer(request: Request) -> Any | None:
    return getattr(request.app.state, "tracer", None)


@contextmanager
def traced_turn(tracer: Any | None, key: MemoryKey) -> Iterator[RunnableConfig | None]:
    """`with traced_turn(tracer, key) as config:` around the turn. Finishes the trace with the error
    class if the turn fails, and re-raises."""
    if tracer is None:
        yield None
        return
    trace = tracer.begin_turn(
        thread_id=key.thread_id, tenant_id=key.tenant_id, user_id=key.user_id, request_id=current_request_id()
    )
    try:
        yield trace.config
    except BaseException as exc:
        trace.finish(error=exc)
        raise
    trace.finish()
