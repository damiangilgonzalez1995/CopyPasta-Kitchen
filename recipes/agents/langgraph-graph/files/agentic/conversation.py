"""One conversation turn: read memory -> run graph -> persist -> answer.

This is what the API calls. Memory is persisted BEFORE answering (or before `done` when
streaming), so a reload right after the answer already sees it.
"""

import logging
from collections.abc import AsyncIterator

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict

from .context import AgentContext
from .graph import EventProcessor, EventType, SSEEvent, ainvoke_graph, astream_graph, run_config
from .memory import Memory, MemoryKey

logger = logging.getLogger(__name__)


class TurnResult(BaseModel):
    """What a turn gives back to the API. `message_id` is the persisted answer (None if nothing
    was stored): the id the client can vote on."""

    model_config = ConfigDict(frozen=True)

    answer: str
    conversation_id: str
    message_id: str | None = None


async def answer_question(
    question: str,
    *,
    key: MemoryKey,
    context: AgentContext,
    memory: Memory,
    config: RunnableConfig | None = None,
) -> TurnResult:
    """`config=None` -> `run_config(key.thread_id)`. Pass one to add observability callbacks."""
    history = await memory.get_messages(key)
    state = await ainvoke_graph(
        question, context=context, history=history, config=config or run_config(key.thread_id)
    )
    message_id = await memory.add_messages(key, state.new_messages)
    return TurnResult(answer=state.answer or "", conversation_id=key.conversation_id, message_id=message_id)


async def stream_answer(
    question: str,
    *,
    key: MemoryKey,
    context: AgentContext,
    memory: Memory,
    config: RunnableConfig | None = None,
) -> AsyncIterator[SSEEvent]:
    """Events of the graph, then `done` with the same fields as `TurnResult`."""
    history = await memory.get_messages(key)
    processor = EventProcessor()
    async for event in astream_graph(
        question, context=context, history=history, config=config or run_config(key.thread_id), processor=processor
    ):
        yield event
        if event.type is EventType.ERROR:
            return

    final = processor.final_state
    message_id = await memory.add_messages(key, final.new_messages) if final is not None else None
    result = TurnResult(
        answer=final.answer or "" if final is not None else "",
        conversation_id=key.conversation_id,
        message_id=message_id,
    )
    yield SSEEvent(type=EventType.DONE, data=result.model_dump())
