"""SQL store (Postgres/Supabase in production, SQLite in tests) with SQLAlchemy 2.

Same pattern as `agent-memory`: the app's `session_factory`, sync queries in `asyncio.to_thread`.
`agent_feedback` has one row per (tenant, user, message). No foreign key to `agent_messages` on
purpose: the recipe does not know your table names; add it in your migration if you want cascade.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, MetaData, String, Table, Text, UniqueConstraint, delete, select
from sqlalchemy.orm import Session

from .base import FeedbackStore
from .models import Feedback

metadata = MetaData()

agent_feedback = Table(
    "agent_feedback",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("user_id", String, nullable=False),
    Column("conversation_id", String, nullable=False, index=True),
    Column("message_id", String, nullable=False),
    Column("rating", Integer, nullable=False),
    Column("comment", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "user_id", "message_id", name="uq_agent_feedback_user_message"),
    CheckConstraint("rating IN (-1, 1)", name="ck_agent_feedback_rating"),
)

COLUMNS = [c.name for c in agent_feedback.c if c.name != "id"]


def _aware(value: datetime) -> datetime:
    """SQLite drops the timezone; Postgres keeps it. Always hand back UTC-aware datetimes."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _row_to_feedback(row) -> Feedback:
    data = dict(row._mapping)
    data.pop("id")
    data["created_at"], data["updated_at"] = _aware(data["created_at"]), _aware(data["updated_at"])
    return Feedback(**data)


class SqlFeedbackStore(FeedbackStore):
    def __init__(self, session_factory: Callable[[], Session], **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_factory = session_factory

    @staticmethod
    def _one(tenant_id: str, user_id: str, message_id: str):
        c = agent_feedback.c
        return (c.tenant_id == tenant_id, c.user_id == user_id, c.message_id == message_id)

    async def get(self, tenant_id: str, user_id: str, message_id: str) -> Feedback | None:
        def run():
            with self._session_factory() as db:
                row = db.execute(select(agent_feedback).where(*self._one(tenant_id, user_id, message_id))).first()
            return _row_to_feedback(row) if row else None

        return await asyncio.to_thread(run)

    async def list_for_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> list[Feedback]:
        def run():
            c = agent_feedback.c
            with self._session_factory() as db:
                rows = db.execute(
                    select(agent_feedback)
                    .where(c.tenant_id == tenant_id, c.user_id == user_id, c.conversation_id == conversation_id)
                    .order_by(c.created_at, c.id)
                ).all()
            return [_row_to_feedback(r) for r in rows]

        return await asyncio.to_thread(run)

    async def remove(self, tenant_id: str, user_id: str, message_id: str) -> bool:
        def run():
            with self._session_factory() as db:
                deleted = db.execute(delete(agent_feedback).where(*self._one(tenant_id, user_id, message_id))).rowcount
                db.commit()
            return deleted > 0

        return await asyncio.to_thread(run)

    async def _save(self, feedback: Feedback) -> None:
        def run():
            # Delete + insert in one transaction: portable upsert. On Postgres under load prefer
            # `insert(...).on_conflict_do_update(...)` from sqlalchemy.dialects.postgresql.
            with self._session_factory() as db:
                db.execute(
                    delete(agent_feedback).where(*self._one(feedback.tenant_id, feedback.user_id, feedback.message_id))
                )
                db.execute(agent_feedback.insert().values(**feedback.model_dump(include=set(COLUMNS))))
                db.commit()

        await asyncio.to_thread(run)
