import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from feedback import FeedbackBackend, FeedbackFactory, FeedbackSettings, FeedbackVote, InMemoryFeedbackStore
from feedback.sql import SqlFeedbackStore, metadata

from .feedback_conformance import FeedbackConformance, clock  # noqa: F401  (fixture)


def sqlite_session_factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    return sessionmaker(engine)


class TestInMemoryFeedbackStore(FeedbackConformance):
    @pytest.fixture
    def store(self, clock):
        return InMemoryFeedbackStore(clock=clock)


class TestSqlFeedbackStore(FeedbackConformance):
    @pytest.fixture
    def store(self, clock):
        return SqlFeedbackStore(sqlite_session_factory(), clock=clock)


# --- Models ----------------------------------------------------------------------------------


def test_rating_is_plus_or_minus_one_and_comment_is_bounded():
    base = dict(tenant_id="t", user_id="u", conversation_id="c", message_id="m")
    with pytest.raises(ValidationError):
        FeedbackVote(**base, rating=0)
    with pytest.raises(ValidationError):
        FeedbackVote(**base, rating=1, comment="x" * 2001)
    assert FeedbackVote(**base, rating=-1).comment is None


# --- Settings + factory: the backend is chosen in .env, not in code ---------------------------


def test_backend_comes_from_env(monkeypatch):
    monkeypatch.setenv("FEEDBACK_BACKEND", "in_memory")
    assert isinstance(FeedbackFactory.create(FeedbackSettings()), InMemoryFeedbackStore)


def test_switching_to_sql_is_only_a_setting():
    store = FeedbackFactory.create(FeedbackSettings(feedback_backend="sql"), session_factory=sqlite_session_factory())
    assert isinstance(store, SqlFeedbackStore)


def test_backend_is_required_and_validated(monkeypatch):
    monkeypatch.delenv("FEEDBACK_BACKEND", raising=False)
    with pytest.raises(ValidationError):
        FeedbackSettings()
    with pytest.raises(ValidationError):
        FeedbackSettings(feedback_backend="redis")
    with pytest.raises(ValueError, match="session_factory"):
        FeedbackFactory.create(FeedbackSettings(feedback_backend=FeedbackBackend.SQL))
