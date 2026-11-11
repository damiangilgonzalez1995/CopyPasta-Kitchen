from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MemoryBackend(StrEnum):
    """Where the conversation lives. Chosen in the settings (`MEMORY_BACKEND`), built by `MemoryFactory`.

    IN_MEMORY: a dict of the process. Lost on restart, not shared between workers: tests and local dev.
    SQL: the `agent_messages` table (Postgres/Supabase in production, SQLite in tests).
    """

    IN_MEMORY = "in_memory"
    SQL = "sql"


class MemoryKey(BaseModel):
    """One conversation thread: the THREE ids, always.

    `conversation_id` is chosen by the client, so using it alone would let tenant B read tenant A's
    thread by guessing it. `tenant_id` and `user_id` come from the auth token, never from the body.
    Frozen: a key that can change between `get` and `add` is a key that can be swapped.
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1, description="Tenant. From the token.")
    user_id: str = Field(min_length=1, description="Who asks. From the token.")
    conversation_id: str = Field(min_length=1, description="The thread. Sent by the client.")

    @property
    def thread_id(self) -> str:
        """Flat id with the server namespace first (for tracing / `run_config`)."""
        return f"{self.tenant_id}:{self.user_id}:{self.conversation_id}"
