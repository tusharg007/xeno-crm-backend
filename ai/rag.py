"""Tiny retrieval helper over project docs for the analytics copilot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config import resolve_path, settings


@dataclass
class RetrievedChunk:
    source: str
    content: str
    score: int


def _docs_dir() -> Path:
    return resolve_path(settings.DOCS_DIR)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def retrieve_docs(query: str, limit: int = 3) -> list[RetrievedChunk]:
    query_tokens = _tokenize(query)
    results: list[RetrievedChunk] = []
    for file_path in sorted(_docs_dir().glob("*.md")):
        content = file_path.read_text(encoding="utf-8")
        score = len(query_tokens.intersection(_tokenize(content)))
        if score:
            results.append(RetrievedChunk(source=file_path.name, content=content[:1200], score=score))
    results.sort(key=lambda chunk: chunk.score, reverse=True)
    return results[:limit]
