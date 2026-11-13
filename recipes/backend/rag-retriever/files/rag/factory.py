"""The one place that builds the embedder, the store and the `Retriever` from settings."""

from collections.abc import Callable
from typing import Any

from .base import Retriever, VectorStore
from .chunking import TextChunker
from .embeddings import Embedder, HashingEmbedder, OpenAIEmbedder
from .models import EmbeddingsProvider, RagBackend
from .settings import RagSettings


class EmbedderFactory:
    @staticmethod
    def create(settings: RagSettings) -> Embedder:
        match settings.embeddings_provider:
            case EmbeddingsProvider.HASHING:
                return HashingEmbedder(dimension=settings.embedding_dimension)
            case EmbeddingsProvider.OPENAI:
                assert settings.openai_api_key is not None  # the settings validator guarantees it
                return OpenAIEmbedder(
                    api_key=settings.openai_api_key,
                    model=settings.embedding_model,
                    dimension=settings.embedding_dimension,
                )
        raise ValueError(f"Unknown embeddings provider: {settings.embeddings_provider!r}")


class VectorStoreFactory:
    @staticmethod
    def create(settings: RagSettings, *, session_factory: Callable[[], Any] | None = None) -> VectorStore:
        dimension = settings.embedding_dimension
        match settings.rag_backend:
            case RagBackend.MEMORY:
                from .in_memory import InMemoryVectorStore

                return InMemoryVectorStore()
            case RagBackend.QDRANT:
                from qdrant_client import AsyncQdrantClient

                from .qdrant import QdrantVectorStore

                key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
                client = AsyncQdrantClient(url=settings.qdrant_url, api_key=key)
                return QdrantVectorStore(client, collection=settings.qdrant_collection, dimension=dimension)
            case RagBackend.PGVECTOR:
                if session_factory is None:
                    raise ValueError("RAG_BACKEND=pgvector needs the app's session_factory")
                from .pgvector import PgVectorStore

                return PgVectorStore(session_factory, dimension=dimension)
        raise ValueError(f"Unknown RAG backend: {settings.rag_backend!r}")


class RagFactory:
    @staticmethod
    def create(
        settings: RagSettings,
        *,
        session_factory: Callable[[], Any] | None = None,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
    ) -> Retriever:
        """Call it once at startup (FastAPI `lifespan`), then `await retriever.store.ensure_ready()`:

            retriever = RagFactory.create(get_settings(), session_factory=SessionLocal)

        `embedder=` / `store=` replace the one the settings would build (tests, custom backends).
        """
        embedder = embedder or EmbedderFactory.create(settings)
        store = store or VectorStoreFactory.create(settings, session_factory=session_factory)
        if embedder.dimension != settings.embedding_dimension:
            raise ValueError(
                f"embedder dimension {embedder.dimension} != EMBEDDING_DIMENSION {settings.embedding_dimension}"
            )
        return Retriever(
            embedder=embedder,
            store=store,
            chunker=TextChunker(size=settings.rag_chunk_size, overlap=settings.rag_chunk_overlap),
            limit=settings.rag_search_limit,
            min_score=settings.rag_min_score,
        )
