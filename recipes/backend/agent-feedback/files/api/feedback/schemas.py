from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from feedback import COMMENT_MAX_LENGTH, Feedback, Rating

ID_PATTERN = r"^[A-Za-z0-9_\-]+$"  # same rule as ChatRequest.conversation_id


class FeedbackRequest(BaseModel):
    """`conversation_id` and `message_id` are what `done` / `ChatResponse` returned for that answer."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str = Field(pattern=ID_PATTERN, max_length=100)
    message_id: str = Field(pattern=ID_PATTERN, max_length=100)
    rating: Rating = Field(description="+1 helpful, -1 not helpful.")
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_id: str
    conversation_id: str
    rating: Rating
    comment: str | None = None
    updated_at: datetime

    @classmethod
    def from_feedback(cls, feedback: Feedback) -> "FeedbackOut":
        return cls(**feedback.model_dump(include=set(cls.model_fields)))


class FeedbackResponse(FeedbackOut):
    created_or_updated: Literal["created", "updated"]


class FeedbackListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: str
    feedback: list[FeedbackOut]
