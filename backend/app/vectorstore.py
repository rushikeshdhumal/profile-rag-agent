from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings

from app.embeddings import embed_query, embed_texts
from app.store import chroma_dir

logger = logging.getLogger(__name__)

MAX_DISTANCE = 0.88

_CHROMA_SETTINGS = Settings(anonymized_telemetry=False, allow_reset=True)


def _client(agent_id: str) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=str(chroma_dir(agent_id)),
        settings=_CHROMA_SETTINGS,
    )


def get_collection(agent_id: str):
    client = _client(agent_id)
    return client.get_or_create_collection(
        name="profile",
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(agent_id: str):
    client = _client(agent_id)
    try:
        client.delete_collection("profile")
    except Exception:
        pass
    return client.get_or_create_collection(
        name="profile",
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    agent_id: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> int:
    if not documents:
        return 0
    collection = reset_collection(agent_id)
    embeddings = embed_texts(documents)
    batch = 100
    for i in range(0, len(documents), batch):
        collection.upsert(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
            embeddings=embeddings[i : i + batch],
        )
    return len(documents)


def query_chunks(
    agent_id: str,
    query: str,
    k: int = 8,
    max_distance: float = MAX_DISTANCE,
) -> list[dict[str, Any]]:
    collection = get_collection(agent_id)
    if collection.count() == 0:
        return []
    embedding = embed_query(query)
    n = min(max(k * 2, k), collection.count())
    result = collection.query(
        query_embeddings=[embedding],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    out: list[dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, distances):
        if dist is not None and dist > max_distance:
            continue
        meta = meta or {}
        out.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "source_type": meta.get("source_type", "other"),
                "distance": dist,
            }
        )
        if len(out) >= k:
            break
    return out


def fetch_chunks_by_source_prefix(agent_id: str, prefix: str, limit: int = 4) -> list[dict[str, Any]]:
    """Pull a few chunks whose source starts with prefix (best-effort via broad query)."""
    collection = get_collection(agent_id)
    count = collection.count()
    if count == 0:
        return []
    raw = collection.get(include=["documents", "metadatas"], limit=min(count, 200))
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    out: list[dict[str, Any]] = []
    for doc, meta in zip(docs, metas):
        meta = meta or {}
        source = str(meta.get("source", ""))
        if source.startswith(prefix) or source == prefix.rstrip("_"):
            out.append(
                {
                    "text": doc,
                    "source": source,
                    "source_type": meta.get("source_type", "other"),
                    "distance": 0.0,
                }
            )
        if len(out) >= limit:
            break
    return out


def fetch_chunks_by_source_type(agent_id: str, source_type: str, limit: int = 8) -> list[dict[str, Any]]:
    collection = get_collection(agent_id)
    count = collection.count()
    if count == 0:
        return []
    raw = collection.get(include=["documents", "metadatas"], limit=min(count, 300))
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    out: list[dict[str, Any]] = []
    for doc, meta in zip(docs, metas):
        meta = meta or {}
        if str(meta.get("source_type", "")) != source_type:
            continue
        out.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "source_type": source_type,
                "distance": 0.0,
            }
        )
        if len(out) >= limit:
            break
    return out
