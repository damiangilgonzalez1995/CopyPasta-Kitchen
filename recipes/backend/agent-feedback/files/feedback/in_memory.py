"""Per-process dict. For tests and local dev only: lost on restart, not shared between workers."""

from .base import FeedbackStore
from .models import Feedback

Key = tuple[str, str, str]  # tenant, user, message


class InMemoryFeedbackStore(FeedbackStore):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._votes: dict[Key, Feedback] = {}

    async def get(self, tenant_id: str, user_id: str, message_id: str) -> Feedback | None:
        return self._votes.get((tenant_id, user_id, message_id))

    async def list_for_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> list[Feedback]:
        mine = [
            f
            for f in self._votes.values()
            if (f.tenant_id, f.user_id, f.conversation_id) == (tenant_id, user_id, conversation_id)
        ]
        return sorted(mine, key=lambda f: f.created_at)

    async def remove(self, tenant_id: str, user_id: str, message_id: str) -> bool:
        return self._votes.pop((tenant_id, user_id, message_id), None) is not None

    async def _save(self, feedback: Feedback) -> None:
        self._votes[(feedback.tenant_id, feedback.user_id, feedback.message_id)] = feedback
