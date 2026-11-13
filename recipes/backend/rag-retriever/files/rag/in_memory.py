"""Vector store in RAM: one process, lost on restart. Development and tests, and the reference
every other backend must match (conformance tests)."""

import math

from .base import VectorStore
from .models import EmbeddedChunk, Filters, SearchHit


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._rows: dict[str, EmbeddedChunk] = {}

    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        for item in chunks:
            self._rows[item.chunk.id] = item

    async def existing_hashes(self, tenant_id: str, document_id: str) -> dict[str, str]:
        return {
            row.chunk.id: row.chunk.content_hash
            for row in self._rows.values()
            if row.chunk.tenant_id == tenant_id and row.chunk.document_id == document_id
        }

    async def delete_chunks(self, tenant_id: str, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            row = self._rows.get(chunk_id)
            if row is not None and row.chunk.tenant_id == tenant_id:
                del self._rows[chunk_id]

    async def delete_document(self, tenant_id: str, document_id: str) -> int:
        ids = list(await self.existing_hashes(tenant_id, document_id))
        await self.delete_chunks(tenant_id, ids)
        return len(ids)

    async def search(
        self, tenant_id: str, vector: list[float], *, limit: int, filters: Filters | None = None
    ) -> list[SearchHit]:
        wanted = filters or {}
        hits = [
            SearchHit(chunk=row.chunk, score=max(0.0, min(1.0, cosine(vector, row.vector))))
            for row in self._rows.values()
            if row.chunk.tenant_id == tenant_id and all(row.chunk.metadata.get(k) == v for k, v in wanted.items())
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.document_id, hit.chunk.chunk_index))
        return hits[:limit]
