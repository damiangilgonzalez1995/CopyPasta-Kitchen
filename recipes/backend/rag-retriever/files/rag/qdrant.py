"""Qdrant backend (`qdrant-client`, async). One collection, payload = the chunk fields, metadata
nested under `metadata`. `tenant_id` and `document_id` get keyword payload indexes.

`AsyncQdrantClient(":memory:")` runs the same code without a server: that is what the tests use.
"""

from typing import Any

from qdrant_client import AsyncQdrantClient, models as q

from .base import VectorStore
from .models import Chunk, EmbeddedChunk, Filters, SearchHit, metadata_of

KEYWORD_FIELDS = ("tenant_id", "document_id")


class QdrantVectorStore(VectorStore):
    def __init__(self, client: AsyncQdrantClient, *, collection: str, dimension: int) -> None:
        self._client = client
        self.collection = collection
        self.dimension = dimension

    async def ensure_ready(self) -> None:
        if not await self._client.collection_exists(self.collection):
            await self._client.create_collection(
                self.collection, vectors_config=q.VectorParams(size=self.dimension, distance=q.Distance.COSINE)
            )
            for field in KEYWORD_FIELDS:
                await self._client.create_payload_index(self.collection, field, q.PayloadSchemaType.KEYWORD)

    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        if chunks:
            await self._client.upsert(
                self.collection,
                points=[q.PointStruct(id=c.chunk.id, vector=c.vector, payload=_payload(c.chunk)) for c in chunks],
            )

    async def existing_hashes(self, tenant_id: str, document_id: str) -> dict[str, str]:
        hashes: dict[str, str] = {}
        offset = None
        while True:
            points, offset = await self._client.scroll(
                self.collection,
                scroll_filter=_filter(tenant_id, document_id=document_id),
                with_payload=["content_hash"],
                with_vectors=False,
                limit=256,
                offset=offset,
            )
            hashes.update({str(p.id): p.payload["content_hash"] for p in points})
            if offset is None:
                return hashes

    async def delete_chunks(self, tenant_id: str, chunk_ids: list[str]) -> None:
        if chunk_ids:
            selector = q.FilterSelector(filter=_filter(tenant_id, ids=chunk_ids))
            await self._client.delete(self.collection, points_selector=selector)

    async def delete_document(self, tenant_id: str, document_id: str) -> int:
        count = len(await self.existing_hashes(tenant_id, document_id))
        if count:
            selector = q.FilterSelector(filter=_filter(tenant_id, document_id=document_id))
            await self._client.delete(self.collection, points_selector=selector)
        return count

    async def search(
        self, tenant_id: str, vector: list[float], *, limit: int, filters: Filters | None = None
    ) -> list[SearchHit]:
        response = await self._client.query_points(
            self.collection, query=vector, limit=limit, with_payload=True, query_filter=_filter(tenant_id, filters=filters)
        )
        return [
            SearchHit(chunk=_chunk(str(p.id), p.payload or {}), score=max(0.0, min(1.0, p.score)))
            for p in response.points
        ]


def _payload(chunk: Chunk) -> dict[str, Any]:
    return chunk.model_dump(exclude={"id"})


def _chunk(point_id: str, payload: dict[str, Any]) -> Chunk:
    return Chunk(id=point_id, **{**payload, "metadata": metadata_of(payload.get("metadata") or {})})


def _filter(
    tenant_id: str, *, document_id: str | None = None, ids: list[str] | None = None, filters: Filters | None = None
) -> q.Filter:
    must: list[Any] = [q.FieldCondition(key="tenant_id", match=q.MatchValue(value=tenant_id))]
    if document_id is not None:
        must.append(q.FieldCondition(key="document_id", match=q.MatchValue(value=document_id)))
    if ids is not None:
        must.append(q.HasIdCondition(has_id=ids))
    for key, value in (filters or {}).items():
        must.append(q.FieldCondition(key=f"metadata.{key}", match=q.MatchValue(value=value)))
    return q.Filter(must=must)
