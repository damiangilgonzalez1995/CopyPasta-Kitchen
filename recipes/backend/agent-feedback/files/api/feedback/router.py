"""POST /agent/feedback (vote), DELETE /agent/feedback/{message_id} (undo), GET /agent/feedback?conversation_id=.

Ownership: the message must be an answer (`ai` with text) inside the caller's own conversation,
read from the same `Memory` the chat writes. Anything else is one 404: unknown message, another
user's, a human message, a tool call. Same guards as the chat (404 when the agent is off, 401).
Mount it next to the chat router: `app.include_router(feedback_router)` after `create_app(...)`.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status

from agentic.memory import Memory, MemoryKey
from feedback import FeedbackStore, FeedbackVote

from ..agent.guards import require_agent_enabled
from ..agent.router import get_memory
from ..auth import CurrentUser, get_current_user
from .schemas import ID_PATTERN, FeedbackListResponse, FeedbackOut, FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/agent/feedback", tags=["agent"], dependencies=[Depends(require_agent_enabled)])


def get_feedback_store(request: Request) -> FeedbackStore:
    store: FeedbackStore | None = getattr(request.app.state, "feedback_store", None)
    if store is None:
        raise RuntimeError("app.state.feedback_store is not set: build it with FeedbackFactory")
    return store


async def is_answer_of(memory: Memory, key: MemoryKey, message_id: str) -> bool:
    """True if `message_id` is an AI message with text in that thread (never a human or tool message)."""
    for item in await memory.get_history(key):
        if item.message.id == message_id:
            return item.message.type == "ai" and bool(str(item.message.text).strip())
    return False


@router.post("", response_model=FeedbackResponse)
async def vote(
    body: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
    memory: Memory = Depends(get_memory),
    store: FeedbackStore = Depends(get_feedback_store),
) -> FeedbackResponse:
    key = MemoryKey(tenant_id=user.tenant_id, user_id=user.id, conversation_id=body.conversation_id)
    if not await is_answer_of(memory, key, body.message_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    result = await store.vote(FeedbackVote(tenant_id=user.tenant_id, user_id=user.id, **body.model_dump()))
    return FeedbackResponse(
        **FeedbackOut.from_feedback(result.feedback).model_dump(),
        created_or_updated="created" if result.created else "updated",
    )


@router.get("", response_model=FeedbackListResponse)
async def list_votes(
    conversation_id: str = Query(pattern=ID_PATTERN, max_length=100),
    user: CurrentUser = Depends(get_current_user),
    store: FeedbackStore = Depends(get_feedback_store),
) -> FeedbackListResponse:
    votes = await store.list_for_conversation(user.tenant_id, user.id, conversation_id)
    return FeedbackListResponse(conversation_id=conversation_id, feedback=[FeedbackOut.from_feedback(v) for v in votes])


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def undo(
    message_id: str = Path(pattern=ID_PATTERN, max_length=100),
    user: CurrentUser = Depends(get_current_user),
    store: FeedbackStore = Depends(get_feedback_store),
) -> Response:
    if not await store.remove(user.tenant_id, user.id, message_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
