"""One conversation turn: read memory -> run graph -> persist -> answer.

This is what the API calls. Memory is persisted BEFORE answering (or before `done` when
streaming), so a reload right after the answer already sees it.
"""

import logging
from collections.abc import AsyncIterator

from .context import AgentContext
from .graph import EventProcessor, EventType, SSEEvent, ainvoke_graph, astream_graph, run_config
from .memory import Memory, MemoryKey

logger = logging.getLogger(__name__)


async def answer_question(question: str, *, key: MemoryKey, context: AgentContext, memory: Memory) -> str:
    history = await memory.get_messages(key)
    state = await ainvoke_graph(
        question, context=context, history=history, config=run_config(key.conversation_id)
    )
    await memory.add_messages(key, state.new_messages)
    return state.answer or ""


async def stream_answer(
    question: str, *, key: MemoryKey, context: AgentContext, memory: Memory
) -> AsyncIterator[SSEEvent]:
    history = await memory.get_messages(key)
    processor = EventProcessor()
    async for event in astream_graph(
        question, context=context, history=history, config=run_config(key.conversation_id), processor=processor
    ):
        yield event
        if event.type is EventType.ERROR:
            return

    if processor.final_state is not None:
        await memory.add_messages(key, processor.final_state.new_messages)
    yield SSEEvent(EventType.DONE, {"answer": processor.final_state.answer if processor.final_state else ""})
