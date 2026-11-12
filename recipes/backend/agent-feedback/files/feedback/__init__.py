"""Thumbs up / down on agent answers. Independent of FastAPI and of the agent.

One vote per (tenant, user, message), upserted. Backend chosen in the settings (`FEEDBACK_BACKEND`),
built by `FeedbackFactory`. Whether the user may vote a message is decided by the caller
(the API checks the message is an answer in the user's own conversation).
"""

from .base import FeedbackStore
from .factory import FeedbackFactory
from .in_memory import InMemoryFeedbackStore
from .models import COMMENT_MAX_LENGTH, Feedback, FeedbackBackend, FeedbackResult, FeedbackVote, Rating
from .settings import FeedbackSettings

__all__ = [
    "COMMENT_MAX_LENGTH",
    "Feedback",
    "FeedbackBackend",
    "FeedbackFactory",
    "FeedbackResult",
    "FeedbackSettings",
    "FeedbackStore",
    "FeedbackVote",
    "InMemoryFeedbackStore",
    "Rating",
]
