"""The one place that builds the store from the backend the settings name. There is no default."""

from collections.abc import Callable
from typing import Any

from .base import Clock, FeedbackStore, utc_now
from .models import FeedbackBackend
from .settings import FeedbackSettings


class FeedbackFactory:
    @staticmethod
    def create(
        settings: FeedbackSettings, *, session_factory: Callable[[], Any] | None = None, clock: Clock = utc_now
    ) -> FeedbackStore:
        """Once at startup:
            app.state.feedback_store = FeedbackFactory.create(get_settings(), session_factory=SessionLocal)
        `SQL` needs the app's `session_factory`. Unknown backend -> ValueError."""
        match settings.feedback_backend:
            case FeedbackBackend.IN_MEMORY:
                from .in_memory import InMemoryFeedbackStore

                return InMemoryFeedbackStore(clock=clock)
            case FeedbackBackend.SQL:
                if session_factory is None:
                    raise ValueError("FEEDBACK_BACKEND=sql needs the app's session_factory")
                from .sql import SqlFeedbackStore

                return SqlFeedbackStore(session_factory, clock=clock)
        raise ValueError(f"Unknown feedback backend: {settings.feedback_backend!r}")
