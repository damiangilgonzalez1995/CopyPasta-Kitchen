import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agentic.memory import InMemoryMemory, MemoryBackend, MemoryFactory, MemoryKey, MemorySettings
from agentic.memory.sql import SqlMemory, metadata

from .memory_conformance import MemoryConformance

WINDOW = 3


def sqlite_session_factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    return sessionmaker(engine)


class TestInMemoryMemory(MemoryConformance):
    @pytest.fixture
    def memory(self):
        return InMemoryMemory(window_turns=WINDOW)


class TestSqlMemory(MemoryConformance):
    @pytest.fixture
    def memory(self):
        return SqlMemory(sqlite_session_factory(), window_turns=WINDOW)


# --- Settings + factory: the backend is chosen in .env, not in code ---------------------------


def test_backend_and_window_come_from_env(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "in_memory")
    monkeypatch.setenv("MEMORY_WINDOW_TURNS", "4")

    memory = MemoryFactory.create(MemorySettings())

    assert isinstance(memory, InMemoryMemory)
    assert memory.window_turns == 4


def test_switching_to_sql_is_only_a_setting():
    settings = MemorySettings(memory_backend="sql")
    memory = MemoryFactory.create(settings, session_factory=sqlite_session_factory())
    assert isinstance(memory, SqlMemory)


def test_backend_is_required(monkeypatch):
    monkeypatch.delenv("MEMORY_BACKEND", raising=False)
    with pytest.raises(ValidationError):
        MemorySettings()


def test_unknown_backend_is_rejected():
    with pytest.raises(ValidationError):
        MemorySettings(memory_backend="redis")


def test_sql_without_session_factory_fails_loudly():
    with pytest.raises(ValueError, match="session_factory"):
        MemoryFactory.create(MemorySettings(memory_backend=MemoryBackend.SQL))


def test_key_rejects_empty_ids_and_is_frozen():
    with pytest.raises(ValidationError):
        MemoryKey(tenant_id="", user_id="u", conversation_id="c")
    key = MemoryKey(tenant_id="t", user_id="u", conversation_id="c")
    with pytest.raises(ValidationError):
        key.tenant_id = "other"
    assert key.thread_id == "t:u:c"
