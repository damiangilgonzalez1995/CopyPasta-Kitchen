import os

import pytest
from pydantic import SecretStr

from rag import (
    Document,
    DocumentSearchService,
    EmbedderFactory,
    HashingEmbedder,
    RagFactory,
    RagSettings,
    RetrievalError,
    Retriever,
    TextChunker,
    VectorStoreFactory,
    format_hits,
)
from rag.in_memory import InMemoryVectorStore
from rag.models import Chunk, SearchHit
from rag.qdrant import QdrantVectorStore

from .rag_conformance import DIMENSION, TENANT, VectorStoreConformance, chunk

# --- backends -------------------------------------------------------------------------------


class TestInMemoryVectorStore(VectorStoreConformance):
    @pytest.fixture
    async def store(self):
        return InMemoryVectorStore()


class TestQdrantVectorStore(VectorStoreConformance):
    @pytest.fixture
    async def store(self):
        from qdrant_client import AsyncQdrantClient

        return QdrantVectorStore(AsyncQdrantClient(":memory:"), collection="test_chunks", dimension=DIMENSION)


@pytest.mark.skipif(not os.environ.get("RAG_TEST_DATABASE_URL"), reason="needs a Postgres with pgvector")
class TestPgVectorStore(VectorStoreConformance):
    @pytest.fixture
    async def store(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from rag.pgvector import TABLE, PgVectorStore

        engine = create_engine(os.environ["RAG_TEST_DATABASE_URL"])
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        return PgVectorStore(sessionmaker(engine), dimension=DIMENSION)


# --- chunking -------------------------------------------------------------------------------


def test_chunker_cuts_at_paragraphs_then_sentences_and_overlaps():
    alpha, beta, gamma = "Alpha one. Alpha two.", "Beta one. Beta two.", "Gamma one. Gamma two."
    pieces = TextChunker(size=45, overlap=10).split("\n\n".join([alpha, beta, gamma]))
    # greedy: the first two paragraphs fit together; the third starts with the overlap, cut at a word
    assert pieces == [f"{alpha}\n\n{beta}", f"two.\n\n{gamma}"]
    sentences = TextChunker(size=25, overlap=0).split(f"{alpha}\n\n{beta}")
    assert sentences == ["Alpha one. Alpha two.", "Beta one. Beta two."]
    assert TextChunker().split("   ") == []
    assert TextChunker(size=30, overlap=0).split("x" * 70) == ["x" * 30, "x" * 30, "x" * 10]


def test_chunker_builds_deterministic_ids_and_hashes():
    document = Document(id="manual.pdf", title="Manual", text="one two\n\nthree four", source="s3://m", metadata={"year": 2026})
    chunks = TextChunker(size=12, overlap=0).chunk(TENANT, document)
    assert [c.text for c in chunks] == ["one two", "three four"]
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert chunks[0].id == Chunk.id_for(TENANT, "manual.pdf", 0) != chunks[1].id
    assert chunks[0].content_hash == Chunk.hash_of("one two")
    assert (chunks[0].title, chunks[0].source, chunks[0].metadata) == ("Manual", "s3://m", {"year": 2026})
    assert TextChunker(size=12, overlap=0).chunk(TENANT, document) == chunks
    with pytest.raises(ValueError):
        TextChunker(size=10, overlap=10)


# --- embedders ------------------------------------------------------------------------------


async def test_hashing_embedder_is_deterministic_and_unit_length():
    embedder = HashingEmbedder(dimension=64)
    a, b = await embedder.embed(["reset the device", "Reset the DEVICE"])
    assert a == b and len(a) == 64 and sum(v * v for v in a) == pytest.approx(1.0)
    assert await embedder.embed([]) == []
    (empty,) = await embedder.embed(["   "])
    assert empty == [0.0] * 64


class ExplodingEmbedder(HashingEmbedder):
    async def _embed(self, texts):
        raise ConnectionError("sk-live-key-leaked in message")


async def test_embedder_failures_become_retrieval_error_without_the_message():
    with pytest.raises(RetrievalError) as info:
        await ExplodingEmbedder().embed(["x"])
    assert (info.value.kind, info.value.stage) == ("ConnectionError", "embed")
    assert "sk-live" not in str(info.value)


class ShortEmbedder(HashingEmbedder):
    async def _embed(self, texts):
        return []


async def test_embedder_must_return_one_vector_per_text():
    with pytest.raises(RetrievalError, match="MissingVectors"):
        await ShortEmbedder().embed(["x"])


# --- retriever ------------------------------------------------------------------------------


class CountingEmbedder(HashingEmbedder):
    def __init__(self) -> None:
        super().__init__(dimension=64)
        self.embedded: list[str] = []

    async def _embed(self, texts):
        self.embedded.extend(texts)
        return await super()._embed(texts)


@pytest.fixture
def embedder() -> CountingEmbedder:
    return CountingEmbedder()


@pytest.fixture
def retriever(embedder) -> Retriever:
    return Retriever(embedder=embedder, store=InMemoryVectorStore(), chunker=TextChunker(size=40, overlap=0), limit=3)


MANUAL = Document(
    id="manual",
    title="Device manual",
    source="https://docs.example/manual",
    text="To reset the device hold the button.\n\nThe battery lasts ten hours.\n\nWarranty covers two years.",
    metadata={"category": "manual"},
)


async def test_index_embeds_only_what_changed_and_drops_stale_chunks(retriever, embedder):
    first = await retriever.index(TENANT, MANUAL)
    assert (first.chunks, first.embedded, first.deleted, first.unchanged) == (3, 3, 0, 0)

    again = await retriever.index(TENANT, MANUAL)
    assert (again.embedded, again.deleted) == (0, 0) and len(embedder.embedded) == 3

    edited = MANUAL.model_copy(update={"text": MANUAL.text.replace("ten hours", "twelve hours")})
    third = await retriever.index(TENANT, edited)
    assert (third.chunks, third.embedded, third.deleted) == (3, 1, 0)
    assert embedder.embedded[-1] == "The battery lasts twelve hours."

    shorter = MANUAL.model_copy(update={"text": "To reset the device hold the button."})
    fourth = await retriever.index(TENANT, shorter)
    assert (fourth.chunks, fourth.embedded, fourth.deleted) == (1, 0, 2)
    assert len(await retriever.store.existing_hashes(TENANT, "manual")) == 1


async def test_search_ranks_by_meaning_filters_and_isolates_tenants(retriever):
    await retriever.index(TENANT, MANUAL)
    await retriever.index(TENANT, Document(id="faq", text="How long does the battery last?", metadata={"category": "faq"}))
    await retriever.index("tenant-2", Document(id="spy", text="reset reset reset the device"))

    hits = await retriever.search(TENANT, "how do I reset the device?")
    assert hits[0].chunk.text == "To reset the device hold the button." and hits[0].score > hits[-1].score
    assert {h.chunk.tenant_id for h in hits} == {TENANT} and len(hits) <= 3

    faq_only = await retriever.search(TENANT, "battery", filters={"category": "faq"})
    assert [h.chunk.document_id for h in faq_only] == ["faq"]

    assert await retriever.search(TENANT, "   ") == []
    assert await retriever.search(TENANT, "battery", min_score=0.99) == []
    assert len(await retriever.search(TENANT, "battery", limit=1)) == 1


async def test_remove_deletes_the_document(retriever):
    await retriever.index(TENANT, MANUAL)
    assert await retriever.remove(TENANT, "manual") == 3
    assert await retriever.search(TENANT, "reset the device") == []


class BrokenStore(InMemoryVectorStore):
    async def search(self, *args, **kwargs):
        raise TimeoutError("postgres://user:password@host/db")


async def test_store_failures_become_retrieval_error_without_the_message(embedder):
    retriever = Retriever(embedder=embedder, store=BrokenStore())
    with pytest.raises(RetrievalError) as info:
        await retriever.search(TENANT, "x")
    assert (info.value.kind, info.value.stage) == ("TimeoutError", "store") and "password" not in str(info.value)


# --- document search service and prompt context --------------------------------------------


async def test_document_search_service_matches_the_agent_tool_protocol(retriever):
    await retriever.index(TENANT, MANUAL)
    service = DocumentSearchService(retriever, filters={"category": "manual"})
    hits = await service.search(TENANT, "reset the device", 2)
    assert len(hits) == 2 and set(hits[0]) == {"title", "snippet", "source", "document_id", "score"}
    assert hits[0]["title"] == "Device manual" and hits[0]["snippet"].startswith("To reset")
    assert await service.search("tenant-2", "reset the device", 2) == []


def test_format_hits_numbers_cites_and_hides_scores():
    hits = [
        SearchHit(chunk=chunk("manual", 0, "Hold the button.\n"), score=0.91),
        SearchHit(chunk=chunk("faq", 3, "Ten hours."), score=0.42),
    ]
    text = format_hits(hits)
    assert text == "[1] Manual (https://docs.example/manual)\nHold the button.\n\n[2] Faq (https://docs.example/faq)\nTen hours."
    assert "0.91" not in text and TENANT not in text
    assert format_hits([]) == "No relevant documents."


# --- settings and factory -------------------------------------------------------------------


def test_settings_require_a_backend_and_what_it_needs():
    with pytest.raises(ValueError, match="rag_backend"):
        RagSettings(_env_file=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        RagSettings(_env_file=None, rag_backend="memory")
    with pytest.raises(ValueError, match="QDRANT_URL"):
        RagSettings(_env_file=None, rag_backend="qdrant", embeddings_provider="hashing")
    with pytest.raises(ValueError, match="OVERLAP"):
        RagSettings(_env_file=None, rag_backend="memory", embeddings_provider="hashing", rag_chunk_size=10, rag_chunk_overlap=10)
    settings = RagSettings(_env_file=None, rag_backend="memory", openai_api_key="sk-test", rag_min_score=0.3)
    assert settings.openai_api_key.get_secret_value() == "sk-test" and settings.rag_min_score == 0.3


def test_factory_builds_the_configured_pieces():
    settings = RagSettings(
        _env_file=None,
        rag_backend="memory",
        embeddings_provider="hashing",
        embedding_dimension=32,
        rag_chunk_size=500,
        rag_chunk_overlap=50,
        rag_search_limit=7,
        rag_min_score=0.2,
    )
    retriever = RagFactory.create(settings)
    assert isinstance(retriever.store, InMemoryVectorStore) and isinstance(retriever.embedder, HashingEmbedder)
    assert retriever.embedder.dimension == 32
    assert (retriever.chunker.size, retriever.chunker.overlap, retriever.limit, retriever.min_score) == (500, 50, 7, 0.2)

    qdrant = VectorStoreFactory.create(settings.model_copy(update={"rag_backend": "qdrant", "qdrant_url": "http://q:6333"}))
    assert isinstance(qdrant, QdrantVectorStore) and qdrant.collection == settings.qdrant_collection

    with pytest.raises(ValueError, match="session_factory"):
        VectorStoreFactory.create(settings.model_copy(update={"rag_backend": "pgvector"}))
    with pytest.raises(ValueError, match="dimension"):
        RagFactory.create(settings, embedder=HashingEmbedder(dimension=8))


def test_openai_embedder_is_built_lazily_with_the_key():
    settings = RagSettings(_env_file=None, rag_backend="memory", openai_api_key=SecretStr("sk-test"), embedding_dimension=256)
    embedder = EmbedderFactory.create(settings)
    assert (embedder.model, embedder.dimension) == ("text-embedding-3-small", 256)
