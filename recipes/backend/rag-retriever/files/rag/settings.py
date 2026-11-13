"""RAG settings BLOCK, meant to be mixed into the project settings (`project-settings` recipe):

    class Settings(RagSettings, LLMSettings, BaseAppSettings): ...

Env vars:
    RAG_BACKEND=memory|qdrant|pgvector        required, no default (RAM is for dev only)
    EMBEDDINGS_PROVIDER=openai|hashing        openai (hashing = local, no network: dev and tests)
    EMBEDDING_MODEL=text-embedding-3-small    EMBEDDING_DIMENSION=1536
    OPENAI_API_KEY=...                        same name as the `langchain-agent` block: one key
    RAG_CHUNK_SIZE=1000  RAG_CHUNK_OVERLAP=200  (characters)
    RAG_SEARCH_LIMIT=5   RAG_MIN_SCORE=0.0       (cosine; 0.0 = keep everything, see RECIPE)
    QDRANT_URL=https://...  QDRANT_API_KEY=...  QDRANT_COLLECTION={{app_name}}_chunks
    (pgvector uses the app's own database: pass `session_factory` to the factory)
"""

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import EmbeddingsProvider, RagBackend


class RagSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    rag_backend: RagBackend = Field(description="Where the vectors live. No default on purpose.")
    embeddings_provider: EmbeddingsProvider = EmbeddingsProvider.OPENAI
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = Field(default=1536, gt=0)
    openai_api_key: SecretStr | None = None

    rag_chunk_size: int = Field(default=1000, gt=0)
    rag_chunk_overlap: int = Field(default=200, ge=0)
    rag_search_limit: int = Field(default=5, ge=1, le=100)
    rag_min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "{{app_name}}_chunks"

    @model_validator(mode="after")
    def _backend_has_what_it_needs(self) -> "RagSettings":
        if self.embeddings_provider is EmbeddingsProvider.OPENAI and self.openai_api_key is None:
            raise ValueError("EMBEDDINGS_PROVIDER=openai needs OPENAI_API_KEY")
        if self.rag_backend is RagBackend.QDRANT and not self.qdrant_url:
            raise ValueError("RAG_BACKEND=qdrant needs QDRANT_URL")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        return self
