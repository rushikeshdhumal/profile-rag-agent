from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _get_cross_encoder():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    settings = get_settings()
    logger.info("Loading cross-encoder reranker %s", settings.rerank_model)
    return TextCrossEncoder(model_name=settings.rerank_model, threads=settings.embedding_threads)


def rerank_chunks(query: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rerank chunks with a CPU ONNX cross-encoder; falls back to input order on failure.

    Feature-flagged (RERANK_ENABLED) since this is the one stage whose latency on
    1-OCPU ARM hardware can't be confirmed without measuring on the target VM.
    """
    if not chunks:
        return chunks
    try:
        encoder = _get_cross_encoder()
    except Exception as exc:
        logger.warning("Reranker unavailable, skipping: %s", exc)
        return chunks

    texts = [c.get("text", "") for c in chunks]
    t0 = time.perf_counter()
    try:
        scores = list(encoder.rerank(query, texts))
    except Exception as exc:
        logger.warning("Reranking failed, skipping: %s", exc)
        return chunks
    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info("rerank pairs=%d elapsed_ms=%.1f", len(texts), elapsed_ms)

    scored = [dict(c, rerank_score=float(s)) for c, s in zip(chunks, scores, strict=True)]
    scored.sort(key=lambda c: c["rerank_score"], reverse=True)
    return scored
