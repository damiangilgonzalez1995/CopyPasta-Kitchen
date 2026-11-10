"""SQL memory (Postgres/Supabase in production, SQLite in tests) with SQLAlchemy 2.

Messages are stored whole with `message_to_dict` so `tool_calls` and `tool_call_id` survive:
without them the history cannot be sent back to the LLM.

Queries are sync and run in a thread (`asyncio.to_thread`) so they never block the event loop.
If your app uses an async engine, swap the two `_sync` methods for async versions.
"""

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, insert, select
from sqlalchemy.orm import Session

from .base import Memory
from .models import MemoryKey

metadata = MetaData()

agent_messages = Table(
    "agent_messages",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("user_id", String, nullable=False),
    Column("conversation_id", String, nullable=False, index=True),
    Column("role", String, nullable=False),
    Column("message", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)),
)


class SqlMemory(Memory):
    def __init__(self, session_factory: Callable[[], Session]) -> None:
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

    async def add_messages(self, key: MemoryKey, messages: Sequence[BaseMessage]) -> None:
        if messages:
            await asyncio.to_thread(self._add_sync, key, list(messages))

    def _add_sync(self, key: MemoryKey, messages: list[BaseMessage]) -> None:
        rows = [
            {
                "tenant_id": key.tenant_id,
                "user_id": key.user_id,
                "conversation_id": key.conversation_id,
                "role": message.type,
                "message": message_to_dict(message),
            }
            for message in messages
        ]
        with self._session_factory() as db:
            db.execute(insert(agent_messages), rows)
            db.commit()

