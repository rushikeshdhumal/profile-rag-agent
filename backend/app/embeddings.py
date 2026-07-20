from __future__ import annotations

import logging
from functools import lru_cache

from fastembed import TextEmbedding

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_embedding_model() -> TextEmbedding:
    settings = get_settings()
    # Map common sentence-transformers id to a FastEmbed ONNX model
    model_name = settings.embedding_model
    if "MiniLM" in model_name or model_name.startswith("sentence-transformers/"):
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
    logger.info("Loading FastEmbed model %s", model_name)
    return TextEmbedding(model_name=model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_embedding_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    return next(model.query_embed(text)).tolist()
