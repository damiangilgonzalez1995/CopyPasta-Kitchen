"""Retrieval layer: documents -> chunks -> vectors in a store chosen by settings -> search by tenant.

    retriever = RagFactory.create(settings, session_factory=SessionLocal)   # startup
    await retriever.store.ensure_ready()
    await retriever.index("tenant-1", Document(id="manual.pdf", title="Manual", text=...))
    hits = await retriever.search("tenant-1", "how do I reset it?")
    ToolSet.default(document_search=DocumentSearchService(retriever))      # agent tool

Backends do not import each other: `rag/` depends on `qdrant-client` or SQLAlchemy only through
the backend you pick in the factory.
"""

from .base import Retriever, VectorStore
from .chunking import TextChunker
from .document_search import DocumentSearchService, format_hits
from .embeddings import Embedder, HashingEmbedder, OpenAIEmbedder
from .factory import EmbedderFactory, RagFactory, VectorStoreFactory
from .models import (
    Chunk,
    Document,
    EmbeddedChunk,
    EmbeddingsProvider,
    Filters,
    IndexResult,
    RagBackend,
    RetrievalError,
    SearchHit,
)
from .settings import RagSettings

__all__ = [
    "Chunk",
    "Document",
    "DocumentSearchService",
    "EmbeddedChunk",
    "Embedder",
    "EmbedderFactory",
    "EmbeddingsProvider",
    "Filters",
    "HashingEmbedder",
    "IndexResult",
    "OpenAIEmbedder",
    "RagBackend",
    "RagFactory",
    "RagSettings",
    "RetrievalError",
    "Retriever",
    "SearchHit",
    "TextChunker",
    "VectorStore",
    "VectorStoreFactory",
    "format_hits",
]
