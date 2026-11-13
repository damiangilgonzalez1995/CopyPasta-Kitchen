"""Postgres + pgvector backend over SQLAlchemy Core (`text()` SQL, synchronous session in
`asyncio.to_thread`, like the other SQL recipes). One table `rag_chunks`, cosine `<=>`.

Needs `CREATE EXTENSION vector` and the table from `schema_sql(dimension)` (run it in your
migration). Only tested against a real Postgres: see `RAG_TEST_DATABASE_URL` in the tests.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import bindparam, text

from .base import VectorStore
from .models import Chunk, EmbeddedChunk, Filters, SearchHit, metadata_of

TABLE = "rag_chunks"


def schema_sql(dimension: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS {TABLE} (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    document_id   TEXT NOT NULL,
    chunk_index   INTEGER NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    source        TEXT,
    text          TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{{}}',
    embedding     vector({dimension}) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_{TABLE}_tenant_document ON {TABLE} (tenant_id, document_id);
CREATE INDEX IF NOT EXISTS ix_{TABLE}_embedding ON {TABLE} USING hnsw (embedding vector_cosine_ops);
"""


class PgVectorStore(VectorStore):
    def __init__(self, session_factory: Callable[[], Any], *, dimension: int) -> None:
        self._session_factory = session_factory
        self.dimension = dimension

    async def ensure_ready(self) -> None:
        def run() -> None:
            with self._session_factory() as session:
                for statement in schema_sql(self.dimension).split(";"):
                    if statement.strip():
                        session.execute(text(statement))
                session.commit()

        await asyncio.to_thread(run)

    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        if not chunks:
            return
        rows = [
            {**c.chunk.model_dump(exclude={"metadata"}), "metadata": json.dumps(c.chunk.metadata), "embedding": _literal(c.vector)}
            for c in chunks
        ]
        await self._run(
            text(f"""
            INSERT INTO {TABLE} (id, tenant_id, document_id, chunk_index, title, source, text, content_hash, metadata, embedding)
            VALUES (:id, :tenant_id, :document_id, :chunk_index, :title, :source, :text, :content_hash,
                    CAST(:metadata AS jsonb), CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title, source = EXCLUDED.source, text = EXCLUDED.text,
                content_hash = EXCLUDED.content_hash, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding
            """),
            rows,
        )

    async def existing_hashes(self, tenant_id: str, document_id: str) -> dict[str, str]:
        rows = await self._run(
            text(f"SELECT id, content_hash FROM {TABLE} WHERE tenant_id = :tenant_id AND document_id = :document_id"),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
        return {row.id: row.content_hash for row in rows}

    async def delete_chunks(self, tenant_id: str, chunk_ids: list[str]) -> None:
        if chunk_ids:
            await self._run(
                text(f"DELETE FROM {TABLE} WHERE tenant_id = :tenant_id AND id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"tenant_id": tenant_id, "ids": chunk_ids},
            )

    async def delete_document(self, tenant_id: str, document_id: str) -> int:
        rows = await self._run(
            text(f"DELETE FROM {TABLE} WHERE tenant_id = :tenant_id AND document_id = :document_id RETURNING id"),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
        return len(rows)

    async def search(
        self, tenant_id: str, vector: list[float], *, limit: int, filters: Filters | None = None
    ) -> list[SearchHit]:
        params: dict[str, Any] = {"tenant_id": tenant_id, "vector": _literal(vector), "limit": limit}
        where = ["tenant_id = :tenant_id"]
        for index, (key, value) in enumerate((filters or {}).items()):
            where.append(f"metadata ->> :fk{index} = :fv{index}")
            params[f"fk{index}"], params[f"fv{index}"] = key, str(value)  # ->> yields text
        rows = await self._run(
            text(f"""
            SELECT id, tenant_id, document_id, chunk_index, title, source, text, content_hash, metadata,
                   1 - (embedding <=> CAST(:vector AS vector)) AS score
            FROM {TABLE} WHERE {" AND ".join(where)}
            ORDER BY embedding <=> CAST(:vector AS vector), document_id, chunk_index LIMIT :limit
            """),
            params,
        )
        hits = []
        for row in rows:
            fields = {k: v for k, v in row._mapping.items() if k != "score"}
            fields["metadata"] = metadata_of(_json(row.metadata))
            hits.append(SearchHit(chunk=Chunk(**fields), score=max(0.0, min(1.0, float(row.score)))))
        return hits

    async def _run(self, statement, params) -> list[Any]:
        def run() -> list[Any]:
            with self._session_factory() as session:
                result = session.execute(statement, params)
                rows = list(result) if result.returns_rows else []
                session.commit()
                return rows

        return await asyncio.to_thread(run)


def _literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


def _json(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value or {})
