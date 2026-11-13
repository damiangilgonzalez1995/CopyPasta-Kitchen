"""Split a document into chunks of about `size` characters with `overlap` characters shared
between neighbours. Recursive: paragraphs first, then lines, sentences, words, characters
(the RecursiveCharacterTextSplitter idea, without the dependency).

Characters, not tokens: close enough for `text-embedding-3-*` (~4 chars per token) and no
tokenizer to ship. If you need token-exact windows, replace `TextChunker.split`.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Chunk, Document

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


class TextChunker(BaseModel):
    model_config = ConfigDict(frozen=True)

    size: int = Field(default=1000, gt=0)
    overlap: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def _overlap_smaller_than_size(self) -> "TextChunker":
        if self.overlap >= self.size:
            raise ValueError("chunk overlap must be smaller than chunk size")
        return self

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        pieces = self._split(text, SEPARATORS)
        return [p for p in self._merge(pieces) if p.strip()]

    def chunk(self, tenant_id: str, document: Document) -> list[Chunk]:
        return [
            Chunk(
                id=Chunk.id_for(tenant_id, document.id, index),
                tenant_id=tenant_id,
                document_id=document.id,
                chunk_index=index,
                text=piece,
                content_hash=Chunk.hash_of(piece),
                title=document.title,
                source=document.source,
                metadata=dict(document.metadata),
            )
            for index, piece in enumerate(self.split(document.text))
        ]

    def _split(self, text: str, separators: list[str]) -> list[str]:
        """Pieces no longer than `size`, cut at the coarsest separator that works."""
        if len(text) <= self.size:
            return [text]
        separator, rest = separators[0], separators[1:]
        parts = list(text) if separator == "" else [p + separator for p in text.split(separator)]
        if separator:
            parts[-1] = parts[-1].removesuffix(separator)
        out: list[str] = []
        for part in parts:
            if not part:
                continue
            out.extend(self._split(part, rest) if len(part) > self.size and rest else [part])
        return out

    def _merge(self, pieces: list[str]) -> list[str]:
        """Greedy merge of small pieces up to `size`, carrying `overlap` chars into the next chunk."""
        chunks: list[str] = []
        current = ""
        for piece in pieces:
            if current and len(current) + len(piece) > self.size:
                chunks.append(current.strip())
                current = self._tail(current)
            current += piece
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _tail(self, text: str) -> str:
        """The last `overlap` characters, started at a word boundary."""
        if not self.overlap:
            return ""
        tail = text[-self.overlap :]
        return tail[tail.index(" ") + 1 :] if " " in tail else tail
