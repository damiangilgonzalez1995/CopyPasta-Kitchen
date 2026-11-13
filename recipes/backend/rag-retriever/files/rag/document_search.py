"""The service the agent's `search_documents` tool expects (recipe `langchain-agent`,
`DocumentSearch` protocol): `search(tenant_id, query, limit) -> list[{"title", "snippet", ...}]`.

Also `format_hits`: the context block for a prompt, numbered, with the citation and WITHOUT scores
or tenant (the LLM reasons on text; scores travel on another channel if the UI needs them).
"""

from pydantic import BaseModel, ConfigDict

from .base import Retriever
from .models import Filters, SearchHit

SNIPPET_LENGTH = 300


class DocumentSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    snippet: str
    source: str | None
    document_id: str
    score: float


class DocumentSearchService:
    def __init__(self, retriever: Retriever, *, filters: Filters | None = None) -> None:
        self._retriever = retriever
        self._filters = filters

    async def search(self, tenant_id: str, query: str, limit: int) -> list[dict]:
        hits = await self._retriever.search(tenant_id, query, limit=limit, filters=self._filters)
        return [
            DocumentSearchResult(
                title=hit.chunk.title or hit.chunk.document_id,
                snippet=snippet(hit.chunk.text),
                source=hit.chunk.source,
                document_id=hit.chunk.document_id,
                score=hit.score,
            ).model_dump()
            for hit in hits
        ]


def snippet(text: str, length: int = SNIPPET_LENGTH) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def format_hits(hits: list[SearchHit], *, empty: str = "No relevant documents.") -> str:
    """`[1] Title (source)\\n<text>` per hit, separated by blank lines."""
    if not hits:
        return empty
    blocks = []
    for number, hit in enumerate(hits, start=1):
        head = hit.chunk.title or hit.chunk.document_id
        if hit.chunk.source:
            head += f" ({hit.chunk.source})"
        blocks.append(f"[{number}] {head}\n{hit.chunk.text.strip()}")
    return "\n\n".join(blocks)
