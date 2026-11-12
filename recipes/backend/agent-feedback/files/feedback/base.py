"""The contract. Every backend passes `tests/feedback_conformance.py`.

    vote(vote)                 upsert by (tenant, user, message): first time `created=True`
    get(...)                   the user's vote on a message, or None
    list_for_conversation(...) the user's votes in a conversation (so the UI restores the thumbs)
    remove(...)                undo a vote; False if there was none

Keys always carry tenant AND user: a vote is private to who cast it. Time comes from `clock`.
Async even in memory: the contract follows the slowest backend.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime

from .models import Feedback, FeedbackResult, FeedbackVote

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class FeedbackStore(ABC):
    def __init__(self, *, clock: Clock = utc_now) -> None:
        self._clock = clock

    async def vote(self, vote: FeedbackVote) -> FeedbackResult:
        """Create the vote or update rating and comment of the existing one (same tenant, user, message)."""
        now = self._clock()
        current = await self.get(vote.tenant_id, vote.user_id, vote.message_id)
        if current is None:
            feedback = Feedback(**vote.model_dump(), created_at=now, updated_at=now)
        else:
            feedback = current.model_copy(update={"rating": vote.rating, "comment": vote.comment, "updated_at": now})
        await self._save(feedback)
        return FeedbackResult(feedback=feedback, created=current is None)

    @abstractmethod
    async def get(self, tenant_id: str, user_id: str, message_id: str) -> Feedback | None: ...

    @abstractmethod
    async def list_for_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> list[Feedback]:
        """The user's votes in that conversation, oldest first. [] if none."""

    @abstractmethod
    async def remove(self, tenant_id: str, user_id: str, message_id: str) -> bool:
        """Delete the vote. True if there was one."""

    @abstractmethod
    async def _save(self, feedback: Feedback) -> None:
        """Insert or replace the row for (tenant, user, message)."""
