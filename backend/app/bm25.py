from __future__ import annotations

import logging
import re
import threading
from typing import Any

from rank_bm25 import BM25Okapi

from app.vectorstore import fetch_all_chunks

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class Bm25Index:
    """Lexical index over one agent's chunks; catches exact terms dense search misses
    (employer names, visa/immigration terms, repo names)."""

    def __init__(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        corpus = [_tokenize(c.get("text", "")) for c in chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, k: int = 10) -> list[dict[str, Any]]:
        if not self._bm25 or not self.chunks:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out: list[dict[str, Any]] = []
        for i in ranked[:k]:
            if scores[i] <= 0:
                continue
            chunk = dict(self.chunks[i])
            chunk["bm25_score"] = float(scores[i])
            out.append(chunk)
        return out


_lock = threading.Lock()
_INDEX_CACHE: dict[str, Bm25Index] = {}


def get_bm25_index(agent_id: str) -> Bm25Index:
    with _lock:
        index = _INDEX_CACHE.get(agent_id)
        if index is None:
            chunks = fetch_all_chunks(agent_id)
            index = Bm25Index(chunks)
            _INDEX_CACHE[agent_id] = index
        return index


def invalidate_bm25_index(agent_id: str) -> None:
    with _lock:
        _INDEX_CACHE.pop(agent_id, None)


def invalidate_all_bm25_indexes() -> None:
    with _lock:
        _INDEX_CACHE.clear()


def search_bm25(agent_id: str, query: str, k: int = 10) -> list[dict[str, Any]]:
    return get_bm25_index(agent_id).search(query, k=k)
