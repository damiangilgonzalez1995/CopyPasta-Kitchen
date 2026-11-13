"""Embedders: `Embedder` is the contract, `OpenAIEmbedder` the real one, `HashingEmbedder` the
local one (deterministic bag of words, no network) for development and tests.

Every embedder states its `model` and `dimension`: the store's collection is created with that
dimension and the chunk hash is only valid for that model, so changing either means re-indexing.
"""

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import SecretStr

from .models import RetrievalError

TOKEN = re.compile(r"\w+", re.UNICODE)


class Embedder(ABC):
    def __init__(self, *, model: str, dimension: int) -> None:
        self.model = model
        self.dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, same order. Any failure -> `RetrievalError(kind, stage="embed")`."""
        if not texts:
            return []
        try:
            vectors = await self._embed(texts)
        except RetrievalError:
            raise
        except Exception as exc:  # the message may hold the API key: keep the class name only
            raise RetrievalError(type(exc).__name__, stage="embed") from None
        if len(vectors) != len(texts):
            raise RetrievalError("MissingVectors", stage="embed")
        return vectors

    @abstractmethod
    async def _embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder(Embedder):
    """Hashing trick: each word lands in a bucket, counts are L2-normalised. Texts sharing words
    get a high cosine, unrelated texts a low one: good enough for tests and local demos."""

    def __init__(self, *, dimension: int = 256) -> None:
        super().__init__(model="hashing", dimension=dimension)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector


class OpenAIEmbedder(Embedder):
    """`text-embedding-3-*` through the official SDK; `dimensions` is sent so the vectors match
    the collection. Batches of `batch_size` texts, output re-ordered by `index`."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        batch_size: int = 100,
        timeout: float = 30.0,
        client: Any | None = None,
    ) -> None:
        super().__init__(model=model, dimension=dimension)
        self.batch_size = batch_size
        if client is None:
            from openai import AsyncOpenAI  # lazy: install `openai` only if you use this provider

            client = AsyncOpenAI(api_key=api_key.get_secret_value(), timeout=timeout)
        self._client = client

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = await self._client.embeddings.create(model=self.model, input=batch, dimensions=self.dimension)
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        return vectors
