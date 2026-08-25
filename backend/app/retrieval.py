from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.bm25 import search_bm25
from app.config import get_settings
from app.rerank import rerank_chunks
from app.vectorstore import query_chunks

logger = logging.getLogger(__name__)

RRF_K = 60
WEIGHT_DENSE = 1.0
WEIGHT_BM25 = 0.7
WEIGHT_INTENT = 0.5

LOGISTICS_SOURCE_TYPES = ("identity", "faq")
EXPERIENCE_SOURCE_TYPES = ("resume", "linkedin")
GITHUB_SOURCE_TYPES = ("github",)

LOGISTICS_RE = re.compile(
    r"\b(relocat\w*|visa|authoriz\w*|authoris\w*|notice|salary|"
    r"compensation|location|locations|remote|hybrid|onsite|on-site|work\s*auth)\b",
    re.I,
)
GITHUB_RE = re.compile(
    r"\b(github|repo|repos|repository|repositories|project|projects|built|stack|"
    r"open[\s-]?source|portfolio|codebase)\b",
    re.I,
)
EXPERIENCE_RE = re.compile(
    r"\b(experience|experiences|work\s+history|employment|career|background|"
    r"jobs?|roles?|positions?|internship|internships|worked|employer|company|"
    r"companies|resume|cv|education|skills?)\b",
    re.I,
)


def _intent_source_types(query: str) -> tuple[str, ...] | None:
    # Experience takes priority: an experience question that also mentions
    # "projects" should still favor resume/linkedin over a generic GitHub prior.
    if EXPERIENCE_RE.search(query):
        return EXPERIENCE_SOURCE_TYPES
    if LOGISTICS_RE.search(query):
        return LOGISTICS_SOURCE_TYPES
    if GITHUB_RE.search(query):
        return GITHUB_SOURCE_TYPES
    return None


def _chunk_key(chunk: dict[str, Any]) -> str:
    return f"{chunk.get('source')}|{chunk.get('text', '')[:60]}"


def _rrf_fuse(ranked_lists: list[tuple[list[dict[str, Any]], float]]) -> list[dict[str, Any]]:
    """Weighted Reciprocal Rank Fusion: combines dense/BM25/intent rankings by
    position rather than by raw score, since cosine distance and BM25 scores
    live on incomparable scales."""
    scores: dict[str, float] = {}
    chunk_by_key: dict[str, dict[str, Any]] = {}
    for chunks, weight in ranked_lists:
        for rank, chunk in enumerate(chunks):
            key = _chunk_key(chunk)
            chunk_by_key.setdefault(key, chunk)
            scores[key] = scores.get(key, 0.0) + weight * (1.0 / (RRF_K + rank + 1))

    ordered_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    out: list[dict[str, Any]] = []
    for key in ordered_keys:
        chunk = dict(chunk_by_key[key])
        chunk["fusion_score"] = scores[key]
        out.append(chunk)
    return out


def retrieve(
    agent_id: str,
    query: str,
    k: int = 8,
    candidate_k: int = 30,
) -> list[dict[str, Any]]:
    """Hybrid retrieval: dense + BM25 + an intent-filtered dense pass, fused with
    RRF, then optionally reranked by a cross-encoder. The regex intent rules
    that used to hard-inject chunks now only nudge ranking (WEIGHT_INTENT),
    so a miscategorized query degrades gracefully instead of losing content."""
    settings = get_settings()
    t0 = time.perf_counter()

    dense = query_chunks(agent_id, query, k=candidate_k)
    t1 = time.perf_counter()

    bm25 = search_bm25(agent_id, query, k=candidate_k)
    t2 = time.perf_counter()

    ranked_lists: list[tuple[list[dict[str, Any]], float]] = [
        (dense, WEIGHT_DENSE),
        (bm25, WEIGHT_BM25),
    ]

    intent_types = _intent_source_types(query)
    if intent_types:
        intent_chunks = query_chunks(
            agent_id,
            query,
            k=candidate_k,
            where={"source_type": {"$in": list(intent_types)}},
        )
        ranked_lists.append((intent_chunks, WEIGHT_INTENT))
    t3 = time.perf_counter()

    fused = _rrf_fuse(ranked_lists)[:candidate_k]

    if settings.rerank_enabled and fused:
        fused = rerank_chunks(query, fused)
    t4 = time.perf_counter()

    logger.info(
        "retrieval agent=%s dense_ms=%.1f bm25_ms=%.1f intent_ms=%.1f rerank_ms=%.1f candidates=%d",
        agent_id,
        (t1 - t0) * 1000,
        (t2 - t1) * 1000,
        (t3 - t2) * 1000,
        (t4 - t3) * 1000,
        len(fused),
    )
    return fused[:k]
