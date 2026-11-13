"""Data of the retrieval layer. Everything is Pydantic; the pieces the stores persist are frozen.

A `Document` is what the app ingests (one PDF, one page, one record). The chunker turns it into
`Chunk`s with a deterministic id (`uuid5(tenant:document:index)`) and a `content_hash`, so
indexing the same document twice is a no-op and changing one paragraph re-embeds one chunk.
"""

import hashlib
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CHUNK_NAMESPACE = uuid.UUID("6f1c9b7e-2d47-4c8b-9e1a-3b5c7d9e1f20")

Scalar = str | int | float | bool
Filters = dict[str, Scalar]
"""Equality filters on `Chunk.metadata` keys (`{"category": "manual"}`). Tenant is never a filter:
it is a mandatory argument everywhere."""


class RagBackend(StrEnum):
    MEMORY = "memory"
    QDRANT = "qdrant"
    PGVECTOR = "pgvector"


class EmbeddingsProvider(StrEnum):
    OPENAI = "openai"
    HASHING = "hashing"  # local, deterministic, no network: dev and tests


class Document(BaseModel):
    """What the app hands to `Retriever.index`. `id` must be stable across re-ingestions
    (a path, a primary key), never random: it is what makes indexing idempotent."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    text: str
    title: str = ""
    source: str | None = Field(default=None, description="URL or path shown to the user as the citation.")
    metadata: dict[str, Scalar] = Field(default_factory=dict, description="Filterable fields (category, year...).")


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    document_id: str
    chunk_index: int = Field(ge=0)
    text: str
    content_hash: str
    title: str = ""
    source: str | None = None
    metadata: dict[str, Scalar] = Field(default_factory=dict)

    @staticmethod
    def id_for(tenant_id: str, document_id: str, chunk_index: int) -> str:
        return str(uuid.uuid5(CHUNK_NAMESPACE, f"{tenant_id}:{document_id}:{chunk_index}"))

    @staticmethod
    def hash_of(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    vector: list[float]


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float = Field(description="Cosine similarity in [0, 1]: 1 = identical direction.")


class IndexResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    chunks: int
    embedded: int = Field(description="Chunks that were new or changed and went through the embedder.")
    deleted: int = Field(description="Stale chunks removed because the document got shorter.")

    @property
    def unchanged(self) -> int:
        return self.chunks - self.embedded


class RetrievalError(Exception):
    """The only error the retrieval path raises. `kind` is the class name of the underlying error,
    never its text (it may carry a connection string or an API key)."""

    def __init__(self, kind: str, *, stage: str) -> None:
        super().__init__(f"{stage}: {kind}")
        self.kind = kind
        self.stage = stage


def metadata_of(payload: dict[str, Any]) -> dict[str, Scalar]:
    return {k: v for k, v in payload.items() if isinstance(v, str | int | float | bool)}
