from __future__ import annotations

import contextlib
import logging
from functools import lru_cache
from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings

from app.embeddings import embed_query, embed_texts
from app.store import chroma_dir

logger = logging.getLogger(__name__)

MAX_DISTANCE = 0.88  # legacy dense-only cutoff; kept as a reference point
LOOSE_MAX_DISTANCE = 1.15  # generous prefilter; the rerank/relevance gate does the real gating

_CHROMA_SETTINGS = Settings(anonymized_telemetry=False, allow_reset=True)

# A single agent's corpus is a few hundred chunks at most, so a generous
# ef makes HNSW search exhaustive-equivalent rather than approximate. This
# also removes a real source of run-to-run nondeterminism in the retrieval
# eval, where near-tied candidates could otherwise flip rank between runs.
_COLLECTION_METADATA = {
    "hnsw:space": "cosine",
    "hnsw:construction_ef": 200,
    "hnsw:search_ef": 200,
    "hnsw:M": 32,
}


@lru_cache(maxsize=64)
def _client_for_path(path: str) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=path, settings=_CHROMA_SETTINGS)


def _client(agent_id: str) -> chromadb.PersistentClient:
    # Keyed by resolved path (not just agent_id) so switching DATA_DIR
    # (e.g. between test runs) can never return a stale client.
    return _client_for_path(str(chroma_dir(agent_id)))


def close_all_clients() -> None:
    """Drop cached PersistentClients so sqlite file handles release.

    Needed before deleting a temp DATA_DIR in tests/evals on platforms
    (e.g. Windows) that refuse to remove files still held open.
    """
    _client_for_path.cache_clear()


def get_collection(agent_id: str):
    client = _client(agent_id)
    return client.get_or_create_collection(
        name="profile",
        metadata=_COLLECTION_METADATA,
    )


def reset_collection(agent_id: str):
    client = _client(agent_id)
    with contextlib.suppress(Exception):
        client.delete_collection("profile")
    return client.get_or_create_collection(
        name="profile",
        metadata=_COLLECTION_METADATA,
    )


def replace_collection(
    agent_id: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> int:
    """Embed into a fresh collection and atomically swap it in.

    Unlike a delete-then-rebuild, live chat keeps serving the old collection
    for the entire (slow) embedding phase; only the final delete+rename is a
    brief window, so a reindex no longer blanks chat mid-rebuild.
    """
    if not documents:
        return 0

    client = _client(agent_id)
    tmp_name = f"profile_tmp_{uuid4().hex[:8]}"
    tmp = client.get_or_create_collection(name=tmp_name, metadata=_COLLECTION_METADATA)

    embeddings = embed_texts(documents)
    batch = 100
    for i in range(0, len(documents), batch):
        tmp.upsert(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
            embeddings=embeddings[i : i + batch],
        )

    with contextlib.suppress(Exception):
        client.delete_collection("profile")
    tmp.modify(name="profile")
    return len(documents)


def query_chunks(
    agent_id: str,
    query: str,
    k: int = 8,
    max_distance: float = LOOSE_MAX_DISTANCE,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    collection = get_collection(agent_id)
    if collection.count() == 0:
        return []
    embedding = embed_query(query)
    n = min(max(k * 2, k), collection.count())
    result = collection.query(
        query_embeddings=[embedding],
        n_results=n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    out: list[dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, distances, strict=True):
        if dist is not None and dist > max_distance:
            continue
        meta = meta or {}
        out.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "source_type": meta.get("source_type", "other"),
                "heading": meta.get("heading", ""),
                "distance": dist,
            }
        )
        if len(out) >= k:
            break
    return out


def fetch_chunks_by_source_type(
    agent_id: str,
    source_type: str | list[str],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Fetch chunks by exact source_type via a native Chroma metadata filter."""
    collection = get_collection(agent_id)
    if collection.count() == 0:
        return []
    types = [source_type] if isinstance(source_type, str) else list(source_type)
    where = {"source_type": {"$in": types}} if len(types) > 1 else {"source_type": types[0]}
    raw = collection.get(where=where, include=["documents", "metadatas"], limit=limit)
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    out: list[dict[str, Any]] = []
    for doc, meta in zip(docs, metas, strict=True):
        meta = meta or {}
        out.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "source_type": meta.get("source_type", "other"),
                "heading": meta.get("heading", ""),
                "distance": 0.0,
            }
        )
    return out


def fetch_all_chunks(agent_id: str, limit: int = 5000) -> list[dict[str, Any]]:
    """Full corpus dump for building the BM25 lexical index (not a filter scan)."""
    collection = get_collection(agent_id)
    count = collection.count()
    if count == 0:
        return []
    raw = collection.get(include=["documents", "metadatas"], limit=min(count, limit))
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    out: list[dict[str, Any]] = []
    for doc, meta in zip(docs, metas, strict=True):
        meta = meta or {}
        out.append(
            {
                "text": doc,
                "source": meta.get("source", "unknown"),
                "source_type": meta.get("source_type", "other"),
                "heading": meta.get("heading", ""),
                "index": meta.get("index", 0),
            }
        )
    return out
