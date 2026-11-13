"""`VectorStore`: the contract every backend implements. `Retriever`: the logic on top of it
(chunk, hash, embed only what changed, drop stale chunks, search with a threshold), which is the
same whatever the backend. A new backend is a `VectorStore` subclass plus the conformance tests.

Tenant isolation is not optional: every method takes `tenant_id` and the backends apply it inside
the query, before any limit. `filters` are equality filters on `Chunk.metadata`.
"""

from abc import ABC, abstractmethod

from .chunking import TextChunker
from .embeddings import Embedder
from .models import Document, EmbeddedChunk, Filters, IndexResult, RetrievalError, SearchHit


class VectorStore(ABC):
    """Storage only. No embedding, no chunking, no scoring policy: that lives in `Retriever`."""

    async def ensure_ready(self) -> None:
        """Create the collection/table if missing. Idempotent; call it once at startup."""

    @abstractmethod
    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        """Insert or replace by `chunk.id`."""

    @abstractmethod
    async def existing_hashes(self, tenant_id: str, document_id: str) -> dict[str, str]:
        """`{chunk_id: content_hash}` of what is stored for the document (empty if unknown)."""

    @abstractmethod
    async def delete_chunks(self, tenant_id: str, chunk_ids: list[str]) -> None: ...

    @abstractmethod
    async def delete_document(self, tenant_id: str, document_id: str) -> int:
        """Remove every chunk of the document. Returns how many were removed."""

    @abstractmethod
    async def search(
        self, tenant_id: str, vector: list[float], *, limit: int, filters: Filters | None = None
    ) -> list[SearchHit]:
        """Top `limit` chunks of the tenant by cosine similarity, best first, no threshold."""


class Retriever:
    """What the app uses. Built by `RagFactory.create(settings, ...)`."""

    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        chunker: TextChunker | None = None,
        limit: int = 5,
        min_score: float = 0.0,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.chunker = chunker or TextChunker()
        self.limit = limit
        self.min_score = min_score

    async def index(self, tenant_id: str, document: Document) -> IndexResult:
        """Idempotent: same text -> nothing embedded; one paragraph changed -> one chunk embedded;
        shorter document -> the chunks past the end are deleted."""
        chunks = self.chunker.chunk(tenant_id, document)
        stored = await self._guard(self.store.existing_hashes(tenant_id, document.id), stage="store")
        changed = [chunk for chunk in chunks if stored.get(chunk.id) != chunk.content_hash]
        if changed:
            vectors = await self.embedder.embed([chunk.text for chunk in changed])
            embedded = [EmbeddedChunk(chunk=chunk, vector=vector) for chunk, vector in zip(changed, vectors, strict=True)]
            await self._guard(self.store.upsert(embedded), stage="store")
        stale = sorted(set(stored) - {chunk.id for chunk in chunks})
        if stale:
            await self._guard(self.store.delete_chunks(tenant_id, stale), stage="store")
        return IndexResult(document_id=document.id, chunks=len(chunks), embedded=len(changed), deleted=len(stale))

    async def remove(self, tenant_id: str, document_id: str) -> int:
        return await self._guard(self.store.delete_document(tenant_id, document_id), stage="store")

    async def search(
        self,
        tenant_id: str,
        query: str,
        *,
        limit: int | None = None,
        filters: Filters | None = None,
        min_score: float | None = None,
    ) -> list[SearchHit]:
        """Best chunks for the query, best first, dropping those under `min_score`."""
        if not query.strip():
            return []
        threshold = self.min_score if min_score is None else min_score
        (vector,) = await self.embedder.embed([query])
        hits = await self._guard(
            self.store.search(tenant_id, vector, limit=limit or self.limit, filters=filters), stage="store"
        )
        return [hit for hit in hits if hit.score >= threshold]

    @staticmethod
    async def _guard(awaitable, *, stage: str):
        try:
            return await awaitable
        except RetrievalError:
            raise
        except Exception as exc:  # connection strings and credentials never leave as text
            raise RetrievalError(type(exc).__name__, stage=stage) from None
