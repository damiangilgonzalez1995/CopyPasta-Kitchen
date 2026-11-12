"""GET /conversations (sidebar), GET /conversations/{id}/messages (history), DELETE /conversations/{id}.

Reads the same `Memory` the chat writes (`app.state.memory`): no second store, no sync.
Every route scopes by the token's tenant and user, so a conversation that is not yours is a 404,
not a 403: the id exists only inside its owner's namespace.
Mount it next to the chat router: `app.include_router(conversations_router)` after `create_app(...)`.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from agentic.memory import Memory, MemoryKey

from ..agent.router import get_memory
from ..auth import CurrentUser, get_current_user
from .schemas import ConversationMessagesResponse, ConversationOut, ConversationsResponse, MessageOut

router = APIRouter(prefix="/conversations", tags=["conversations"])

ConversationId = Path(pattern=r"^[A-Za-z0-9_\-]+$", max_length=100)  # same rule as ChatRequest.conversation_id


def conversation_key(
    conversation_id: str = ConversationId, user: CurrentUser = Depends(get_current_user)
) -> MemoryKey:
    return MemoryKey(tenant_id=user.tenant_id, user_id=user.id, conversation_id=conversation_id)


@router.get("", response_model=ConversationsResponse)
async def list_conversations(
    user: CurrentUser = Depends(get_current_user),
    memory: Memory = Depends(get_memory),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationsResponse:
    summaries = await memory.list_conversations(user.tenant_id, user.id, limit=limit, offset=offset)
    return ConversationsResponse(conversations=[ConversationOut.from_summary(s) for s in summaries])


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def conversation_messages(
    key: MemoryKey = Depends(conversation_key), memory: Memory = Depends(get_memory)
) -> ConversationMessagesResponse:
    history = await memory.get_history(key)
    if not history:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    messages = [m for m in (MessageOut.from_history(item) for item in history) if m is not None]
    return ConversationMessagesResponse(conversation_id=key.conversation_id, messages=messages)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(key: MemoryKey = Depends(conversation_key), memory: Memory = Depends(get_memory)) -> Response:
    if not await memory.get_history(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    await memory.clear(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
