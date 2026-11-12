"""What the sidebar and the history view receive. Built from `agent-memory` models, never exposed raw."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic.memory import ConversationSummary, HistoryMessage

ROLES: dict[str, str] = {"human": "user", "ai": "assistant"}


class ConversationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(ge=0)

    @classmethod
    def from_summary(cls, summary: ConversationSummary) -> "ConversationOut":
        return cls(**summary.model_dump())


class ConversationsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversations: list[ConversationOut]


class MessageOut(BaseModel):
    """Only what a chat renders: user and assistant text. Tool calls and results stay in the DB."""

    model_config = ConfigDict(frozen=True)

    id: str | None = Field(default=None, description="The stored message id (what `agent-feedback` votes on).")
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    @classmethod
    def from_history(cls, item: HistoryMessage) -> "MessageOut | None":
        """None for messages the UI does not show (tool calls, tool results, empty AI messages)."""
        role = ROLES.get(item.message.type)
        content = str(item.message.text).strip()
        if role is None or not content:
            return None
        return cls(id=item.message.id, role=role, content=content, created_at=item.created_at)


class ConversationMessagesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: str
    messages: list[MessageOut]
