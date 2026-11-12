"""SQL memory (Postgres/Supabase in production, SQLite in tests) with SQLAlchemy 2.

Messages are stored whole with `message_to_dict` so `tool_calls` and `tool_call_id` survive:
without them the history cannot be sent back to the LLM.

The session factory is the app's (`SessionLocal`): memory shares the app database, it does not
open its own connection. Queries are sync and run in a thread (`asyncio.to_thread`) so they never
block the event loop. With an async engine, swap the `_sync` methods for async versions.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Session

from .base import Memory
from .models import ConversationSummary, HistoryMessage, MemoryKey, title_from

metadata = MetaData()

agent_messages = Table(
    "agent_messages",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("user_id", String, nullable=False),
    Column("conversation_id", String, nullable=False, index=True),
    Column("message_id", String, nullable=True),  # NULL allowed: messages without id are always appended
    Column("role", String, nullable=False),
    Column("message", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)),
    UniqueConstraint("tenant_id", "user_id", "conversation_id", "message_id", name="uq_agent_messages_thread_msg"),
)


def _aware(value: datetime) -> datetime:
    """SQLite drops the timezone; Postgres keeps it. Always hand back UTC-aware datetimes."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class SqlMemory(Memory):
    def __init__(self, session_factory: Callable[[], Session], **kwargs) -> None:
        super().__init__(**kwargs)
        self._session_factory = session_factory

    @staticmethod
    def _thread(query, key: MemoryKey):
        """The ONLY place that filters by thread: always the three ids."""
        return query.where(
            agent_messages.c.tenant_id == key.tenant_id,
            agent_messages.c.user_id == key.user_id,
            agent_messages.c.conversation_id == key.conversation_id,
        )

    async def _fetch_recent_turns(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        return await asyncio.to_thread(self._fetch_sync, key, turns)

    def _fetch_sync(self, key: MemoryKey, turns: int) -> list[BaseMessage]:
        with self._session_factory() as db:
            start = db.execute(
                self._thread(select(agent_messages.c.seq), key)
                .where(agent_messages.c.role == "human")
                .order_by(agent_messages.c.seq.desc())
                .limit(1)
                .offset(turns - 1)
            ).scalar()
            query = self._thread(select(agent_messages.c.message), key)
            if start is not None:
                query = query.where(agent_messages.c.seq >= start)
            rows = db.execute(query.order_by(agent_messages.c.seq)).scalars().all()
        return messages_from_dict(list(rows))

    async def _append(self, key: MemoryKey, messages: list[BaseMessage]) -> None:
        await asyncio.to_thread(self._append_sync, key, messages, self._clock())

    def _append_sync(self, key: MemoryKey, messages: list[BaseMessage], now: datetime) -> None:
        ids = [m.id for m in messages if m.id]
        with self._session_factory() as db:
            seen = set()
            if ids:
                seen = set(
                    db.execute(
                        self._thread(select(agent_messages.c.message_id), key).where(
                            agent_messages.c.message_id.in_(ids)
                        )
                    ).scalars()
                )
            rows = []
            for message in messages:
                if message.id and message.id in seen:
                    continue
                if message.id:
                    seen.add(message.id)
                rows.append(
                    {
                        "tenant_id": key.tenant_id,
                        "user_id": key.user_id,
                        "conversation_id": key.conversation_id,
                        "message_id": message.id,
                        "role": message.type,
                        "message": message_to_dict(message),
                        "created_at": now,
                    }
                )
            if rows:
                db.execute(agent_messages.insert(), rows)
                db.commit()

    async def get_history(self, key: MemoryKey) -> list[HistoryMessage]:
        return await asyncio.to_thread(self._history_sync, key)

    def _history_sync(self, key: MemoryKey) -> list[HistoryMessage]:
        with self._session_factory() as db:
            rows = db.execute(
                self._thread(select(agent_messages.c.message, agent_messages.c.created_at), key).order_by(
                    agent_messages.c.seq
                )
            ).all()
        return [
            HistoryMessage(message=messages_from_dict([message])[0], created_at=_aware(created_at))
            for message, created_at in rows
        ]

    async def list_conversations(
        self, tenant_id: str, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[ConversationSummary]:
        return await asyncio.to_thread(self._list_sync, tenant_id, user_id, limit, offset)

    def _list_sync(self, tenant_id: str, user_id: str, limit: int, offset: int) -> list[ConversationSummary]:
        c = agent_messages.c
        mine = (c.tenant_id == tenant_id, c.user_id == user_id)
        with self._session_factory() as db:
            # One row per conversation, newest activity first (seq is monotonic, so max(seq) orders by update).
            page = db.execute(
                select(c.conversation_id, func.min(c.created_at), func.max(c.created_at), func.count(), func.max(c.seq))
                .where(*mine)
                .group_by(c.conversation_id)
                .order_by(func.max(c.seq).desc())
                .limit(limit)
                .offset(offset)
            ).all()
            if not page:
                return []
            # The first human message of each conversation on the page: its title.
            first_human = (
                select(c.conversation_id, func.min(c.seq).label("seq"))
                .where(*mine, c.role == "human", c.conversation_id.in_([row[0] for row in page]))
                .group_by(c.conversation_id)
                .subquery()
            )
            titles = {
                conversation_id: title_from(messages_from_dict([message])[0].text)
                for conversation_id, message in db.execute(
                    select(c.conversation_id, c.message).join(first_human, c.seq == first_human.c.seq)
                ).all()
            }
        return [
            ConversationSummary(
                conversation_id=conversation_id,
                title=titles.get(conversation_id, ""),
                created_at=_aware(created_at),
                updated_at=_aware(updated_at),
                message_count=count,
            )
            for conversation_id, created_at, updated_at, count, _ in page
        ]

    async def clear(self, key: MemoryKey) -> None:
        await asyncio.to_thread(self._clear_sync, key)

    def _clear_sync(self, key: MemoryKey) -> None:
        with self._session_factory() as db:
            db.execute(self._thread(delete(agent_messages), key))
            db.commit()
