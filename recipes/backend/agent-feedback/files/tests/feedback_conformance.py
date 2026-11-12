"""Behaviour every `FeedbackStore` backend must have. A new backend = a subclass with a `store` fixture.

    class TestRedisFeedbackStore(FeedbackConformance):
        @pytest.fixture
        def store(self, clock): return RedisFeedbackStore(redis, clock=clock)
"""

from datetime import UTC, datetime, timedelta

import pytest

from feedback import FeedbackVote

START = datetime(2026, 3, 30, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def vote(message_id: str = "a1", rating: int = 1, *, user_id: str = "user-1", tenant_id: str = "tenant-1", **kw) -> FeedbackVote:
    return FeedbackVote(
        tenant_id=tenant_id, user_id=user_id, conversation_id=kw.pop("conversation_id", "conv-1"), message_id=message_id, rating=rating, **kw
    )


class FeedbackConformance:
    async def test_unknown_vote_is_none_and_remove_is_false(self, store):
        assert await store.get("tenant-1", "user-1", "a1") is None
        assert await store.remove("tenant-1", "user-1", "a1") is False
        assert await store.list_for_conversation("tenant-1", "user-1", "conv-1") == []

    async def test_first_vote_is_created_with_timestamps(self, store):
        result = await store.vote(vote(rating=1, comment="útil"))

        assert result.created is True
        assert (result.feedback.rating, result.feedback.comment) == (1, "útil")
        assert result.feedback.created_at == result.feedback.updated_at == START
        assert await store.get("tenant-1", "user-1", "a1") == result.feedback

    async def test_voting_again_updates_rating_and_comment_but_keeps_created_at(self, store, clock):
        await store.vote(vote(rating=1, comment="útil"))
        clock.advance(60)

        result = await store.vote(vote(rating=-1))

        assert result.created is False
        assert (result.feedback.rating, result.feedback.comment) == (-1, None)
        assert (result.feedback.created_at, result.feedback.updated_at) == (START, START + timedelta(seconds=60))
        assert len(await store.list_for_conversation("tenant-1", "user-1", "conv-1")) == 1

    async def test_votes_are_private_to_tenant_and_user(self, store):
        await store.vote(vote(rating=1))
        await store.vote(vote(rating=-1, user_id="user-2"))
        await store.vote(vote(rating=-1, tenant_id="tenant-2"))

        assert (await store.get("tenant-1", "user-1", "a1")).rating == 1
        assert (await store.get("tenant-1", "user-2", "a1")).rating == -1
        assert [f.rating for f in await store.list_for_conversation("tenant-1", "user-1", "conv-1")] == [1]

    async def test_list_for_conversation_is_oldest_first_and_scoped(self, store, clock):
        await store.vote(vote("a2", -1))
        clock.advance(1)
        await store.vote(vote("a1", 1))
        await store.vote(vote("a9", 1, conversation_id="conv-2"))

        votes = await store.list_for_conversation("tenant-1", "user-1", "conv-1")

        assert [(f.message_id, f.rating) for f in votes] == [("a2", -1), ("a1", 1)]

    async def test_remove_deletes_only_that_vote(self, store):
        await store.vote(vote("a1"))
        await store.vote(vote("a2"))

        assert await store.remove("tenant-1", "user-1", "a1") is True
        assert await store.get("tenant-1", "user-1", "a1") is None
        assert await store.get("tenant-1", "user-1", "a2") is not None
