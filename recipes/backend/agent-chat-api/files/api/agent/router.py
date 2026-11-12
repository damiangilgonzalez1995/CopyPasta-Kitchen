"""POST /agent/chat (JSON) and POST /agent/stream (SSE): the same turn, two ways of answering.

Thin controller: guards -> sanitize -> build the key and the context from the token -> run the turn
(`agentic.conversation`). It knows nothing about the graph or the LLM.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from agentic.context import AgentContext
from agentic.conversation import answer_question, stream_answer
from agentic.graph import EventType, SSEEvent
from agentic.memory import Memory, MemoryKey

from ..auth import CurrentUser
from .guards import ensure_turn_allowed, get_agent_api_settings, require_agent_enabled
from .sanitize import sanitize_question
from .schemas import ChatRequest, ChatResponse
from .settings import AgentApiSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_agent_enabled)])


def get_memory(request: Request) -> Memory:
    memory: Memory | None = getattr(request.app.state, "memory", None)
    if memory is None:
        raise RuntimeError("app.state.memory is not set: build the app with a Memory (MemoryFactory)")
    return memory


class Turn:
    """What both endpoints need, built once: clean question, memory key and agent context."""

    def __init__(self, body: ChatRequest, user: CurrentUser, settings: AgentApiSettings) -> None:
        self.question = sanitize_question(body.question, max_length=settings.chat_max_question_length)
        conversation_id = body.conversation_id or str(uuid.uuid4())
        # The three ids. The client only chooses the last one; the other two come from the token.
        self.key = MemoryKey(tenant_id=user.tenant_id, user_id=user.id, conversation_id=conversation_id)
        self.context = AgentContext(
            tenant_id=user.tenant_id, user_id=user.id, language=body.language or user.language
        )


def prepare_turn(
    body: ChatRequest,
    user: CurrentUser = Depends(ensure_turn_allowed),
    settings: AgentApiSettings = Depends(get_agent_api_settings),
) -> Turn:
    return Turn(body, user, settings)


@router.post("/chat", response_model=ChatResponse)
async def chat(turn: Turn = Depends(prepare_turn), memory: Memory = Depends(get_memory)) -> ChatResponse:
    result = await answer_question(turn.question, key=turn.key, context=turn.context, memory=memory)
    return ChatResponse(**result.model_dump())


@router.post("/stream")
async def stream(turn: Turn = Depends(prepare_turn), memory: Memory = Depends(get_memory)) -> EventSourceResponse:
    """Same turn as `/chat`, answered as SSE events (see `agentic/graph/events.py`). Ends with
    `done` (same fields as `ChatResponse`) or `error` with a correlation id, never with details."""

    async def events():
        try:
            async for event in stream_answer(turn.question, key=turn.key, context=turn.context, memory=memory):
                yield event.to_sse()
        except Exception:  # outside the graph (memory, network): the graph already guards its own
            error_id = uuid.uuid4().hex[:12]
            logger.exception("Chat stream failed (error_id=%s, thread=%s)", error_id, turn.key.thread_id)
            yield SSEEvent(type=EventType.ERROR, data={"error_id": error_id}).to_sse()

    return EventSourceResponse(events())
