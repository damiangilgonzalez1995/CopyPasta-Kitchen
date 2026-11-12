"""Entry points of the graph: one turn as JSON (`ainvoke_graph`) or as SSE events (`astream_graph`)."""

import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from ..context import AgentContext
from .builder import compile_graph
from .event_processor import EventProcessor
from .events import EventType, SSEEvent
from .state import GraphState

logger = logging.getLogger(__name__)


def run_config(thread_id: str, callbacks: Sequence[Any] = ()) -> RunnableConfig:
    """Observability goes here (Langfuse/Opik/LangSmith callbacks + metadata), never in the core."""
    return {"callbacks": list(callbacks), "metadata": {"thread_id": thread_id}}


async def ainvoke_graph(
    question: str,
    *,
    context: AgentContext,
    history: Sequence[BaseMessage] = (),
    config: RunnableConfig | None = None,
) -> GraphState:
    graph = compile_graph()
    result = await graph.ainvoke(
        GraphState(question=question, history=list(history)), context=context, config=config
    )
    return GraphState.model_validate(result)


async def astream_graph(
    question: str,
    *,
    context: AgentContext,
    history: Sequence[BaseMessage] = (),
    config: RunnableConfig | None = None,
    processor: EventProcessor | None = None,
) -> AsyncIterator[SSEEvent]:
    """Yields events; the final state is left in `processor.final_state`. Errors -> one `error` event
    with a correlation id (details only in the logs)."""
    graph = compile_graph()
    processor = processor or EventProcessor()
    try:
        async for raw in graph.astream_events(
            GraphState(question=question, history=list(history)), context=context, config=config, version="v2"
        ):
            for event in processor.process(raw):
                yield event
    except Exception:
        error_id = uuid.uuid4().hex[:12]
        logger.exception("Graph stream failed (error_id=%s)", error_id)
        yield SSEEvent(type=EventType.ERROR, data={"error_id": error_id})
