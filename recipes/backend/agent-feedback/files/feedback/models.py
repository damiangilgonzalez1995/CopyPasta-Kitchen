from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# +1 helpful, -1 not helpful. Integers so dashboards can SUM/AVG without converting.
Rating = Literal[-1, 1]

COMMENT_MAX_LENGTH = 2000


class FeedbackBackend(StrEnum):
    """Where votes live. Chosen in the settings (`FEEDBACK_BACKEND`), built by `FeedbackFactory`.

    IN_MEMORY: a dict of the process. Lost on restart: tests and local dev.
    SQL: the `agent_feedback` table (Postgres/Supabase in production, SQLite in tests).
    """

    IN_MEMORY = "in_memory"
    SQL = "sql"


class FeedbackVote(BaseModel):
    """What a user says about one answer. Tenant and user come from the token, never from the body."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1, description="The stored answer (`message_id` of `done` / `ChatResponse`).")
    rating: Rating
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)


class Feedback(FeedbackVote):
    """A stored vote. One per (tenant, user, message): voting again updates it."""

    created_at: datetime
    updated_at: datetime


class FeedbackResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    feedback: Feedback
    created: bool = Field(description="True on the first vote, False when an existing one was updated.")
