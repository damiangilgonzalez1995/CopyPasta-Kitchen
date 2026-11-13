"""Behaviour every `VectorStore` backend must have. A new backend = a subclass with a `store` fixture.

    class TestRedisVectorStore(VectorStoreConformance):
        @pytest.fixture
        async def store(self): ...

Vectors are 4-dimensional here (`DIMENSION`): build the backend's collection with it.
"""

import pytest

from rag.models import Chunk, EmbeddedChunk

DIMENSION = 4
TENANT = "tenant-1"
OTHER_TENANT = "tenant-2"


def chunk(document_id: str, index: int, text: str, *, tenant_id: str = TENANT, **metadata) -> Chunk:
    return Chunk(
        id=Chunk.id_for(tenant_id, document_id, index),
        tenant_id=tenant_id,
        document_id=document_id,
        chunk_index=index,
        text=text,
        content_hash=Chunk.hash_of(text),
        title=document_id.title(),
        source=f"https://docs.example/{document_id}",
        metadata=metadata,
    )


def embedded(document_id: str, index: int, vector: list[float], *, tenant_id: str = TENANT, **metadata) -> EmbeddedChunk:
    return EmbeddedChunk(chunk=chunk(document_id, index, f"{document_id} #{index}", tenant_id=tenant_id, **metadata), vector=vector)


ROWS = [
    embedded("manual", 0, [1, 0, 0, 0], category="manual"),
    embedded("manual", 1, [0.9, 0.1, 0, 0], category="manual"),
    embedded("faq", 0, [0, 1, 0, 0], category="faq"),
    embedded("secret", 0, [1, 0, 0, 0], tenant_id=OTHER_TENANT, category="manual"),
]


class VectorStoreConformance:
    @pytest.fixture
    async def filled(self, store):
        await store.ensure_ready()
        await store.upsert(ROWS)
        return store

    async def test_search_orders_by_cosine_and_respects_limit(self, filled):
        hits = await filled.search(TENANT, [1, 0, 0, 0], limit=2)
        assert [(h.chunk.document_id, h.chunk.chunk_index) for h in hits] == [("manual", 0), ("manual", 1)]
        assert hits[0].score == pytest.approx(1.0) and 0.9 < hits[1].score < 1.0
        assert hits[0].chunk == ROWS[0].chunk  # title, source and metadata round-trip

    async def test_tenant_is_filtered_inside_the_query(self, filled):
        hits = await filled.search(OTHER_TENANT, [1, 0, 0, 0], limit=10)
        assert [h.chunk.document_id for h in hits] == ["secret"]
        assert await filled.existing_hashes(OTHER_TENANT, "manual") == {}

    async def test_metadata_filters_are_equality(self, filled):
        hits = await filled.search(TENANT, [1, 0, 0, 0], limit=10, filters={"category": "faq"})
        assert [h.chunk.document_id for h in hits] == ["faq"]
        assert await filled.search(TENANT, [1, 0, 0, 0], limit=10, filters={"category": "nope"}) == []

    async def test_upsert_replaces_by_id(self, filled):
        changed = embedded("manual", 0, [0, 0, 0, 1], category="manual")
        await filled.upsert([changed])
        assert await filled.existing_hashes(TENANT, "manual") == {
            changed.chunk.id: changed.chunk.content_hash,
            ROWS[1].chunk.id: ROWS[1].chunk.content_hash,
        }
        best = (await filled.search(TENANT, [0, 0, 0, 1], limit=1))[0]
        assert best.chunk.id == changed.chunk.id and best.chunk.text == changed.chunk.text

    async def test_delete_chunks_only_touches_the_tenant(self, filled):
        await filled.delete_chunks(OTHER_TENANT, [ROWS[0].chunk.id])
        assert ROWS[0].chunk.id in await filled.existing_hashes(TENANT, "manual")
        await filled.delete_chunks(TENANT, [ROWS[0].chunk.id, "missing-id"])
        assert list(await filled.existing_hashes(TENANT, "manual")) == [ROWS[1].chunk.id]

    async def test_delete_document_returns_the_count(self, filled):
        assert await filled.delete_document(TENANT, "manual") == 2
        assert await filled.delete_document(TENANT, "manual") == 0
        assert [h.chunk.document_id for h in await filled.search(TENANT, [1, 0, 0, 0], limit=10)] == ["faq"]
        assert await filled.existing_hashes(OTHER_TENANT, "secret") != {}

    async def test_empty_store_and_empty_upsert(self, store):
        await store.ensure_ready()
        await store.ensure_ready()  # idempotent
        await store.upsert([])
        assert await store.search(TENANT, [1, 0, 0, 0], limit=5) == []
        assert await store.existing_hashes(TENANT, "manual") == {}
