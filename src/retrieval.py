from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    heading_path: tuple[str, ...]
    source_url: str
    publisher: str
    audience: str
    age_applicability: str
    country: str
    language: str
    topic_tags: tuple[str, ...]
    source_date: str | None
    collection_date: str
    rights_record: str
    review_state: str
    content_hash: str

    @classmethod
    def from_dict(cls, item: dict) -> "Chunk":
        return cls(
            chunk_id=item["chunk_id"],
            document_id=item["document_id"],
            text=item["text"],
            heading_path=tuple(item.get("heading_path", [])),
            source_url=item["source_url"],
            publisher=item["publisher"],
            audience=item["audience"],
            age_applicability=item["age_applicability"],
            country=item["country"],
            language=item.get("language", "en"),
            topic_tags=tuple(item.get("topic_tags", [])),
            source_date=item.get("source_date"),
            collection_date=item["collection_date"],
            rights_record=item["rights_record"],
            review_state=item["review_state"],
            content_hash=item["content_hash"],
        )


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


class KeywordRetriever:
    """Small reproducible baseline; only eligible reviewed chunks may be returned."""

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self.chunks = list(chunks)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "KeywordRetriever":
        chunks: list[Chunk] = []
        source = Path(path)
        if not source.exists():
            return cls([])
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunks.append(Chunk.from_dict(json.loads(line)))
        return cls(chunks)

    def search(
        self,
        query: str,
        *,
        topics: set[str] | None = None,
        country: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        query_tokens = set(TOKEN_RE.findall(query.lower()))
        if not query_tokens:
            return []
        results: list[SearchResult] = []
        for chunk in self.chunks:
            if chunk.review_state != "clinically_reviewed_eligible":
                continue
            if topics and not topics.intersection(chunk.topic_tags):
                continue
            if country and chunk.country not in {country, "general", "unknown"}:
                continue
            text_tokens = set(TOKEN_RE.findall((" ".join(chunk.heading_path) + " " + chunk.text).lower()))
            overlap = query_tokens.intersection(text_tokens)
            if not overlap:
                continue
            score = len(overlap) / len(query_tokens)
            results.append(SearchResult(chunk=chunk, score=score))
        return sorted(results, key=lambda item: (-item.score, item.chunk.chunk_id))[:limit]

