from __future__ import annotations

from app.bm25 import get_bm25_index, invalidate_bm25_index, search_bm25
from app.vectorstore import replace_collection

AGENT_ID = "bm25-test-agent"


def _seed() -> None:
    ids = ["c1", "c2", "c3"]
    documents = [
        "Ada requires H-1B visa sponsorship for future employment.",
        "Ada enjoys hiking and photography on weekends.",
        "The rag-toolkit repository combines BM25 and dense retrieval.",
    ]
    metadatas = [
        {"source": "faq_work_authorization.md", "source_type": "faq", "index": 0, "heading": "", "char_start": 0},
        {"source": "blog_notes.md", "source_type": "blog", "index": 0, "heading": "", "char_start": 0},
        {"source": "github_repo_rag_toolkit.md", "source_type": "github", "index": 0, "heading": "", "char_start": 0},
    ]
    replace_collection(AGENT_ID, ids, documents, metadatas)


def test_search_bm25_finds_exact_term_match():
    _seed()
    invalidate_bm25_index(AGENT_ID)
    results = search_bm25(AGENT_ID, "H-1B visa", k=3)
    assert results
    assert results[0]["source"] == "faq_work_authorization.md"


def test_search_bm25_empty_agent_returns_empty():
    assert search_bm25("bm25-nonexistent-agent", "anything", k=3) == []


def test_bm25_index_is_cached_until_invalidated():
    _seed()
    invalidate_bm25_index(AGENT_ID)
    first = get_bm25_index(AGENT_ID)
    second = get_bm25_index(AGENT_ID)
    assert first is second

    invalidate_bm25_index(AGENT_ID)
    third = get_bm25_index(AGENT_ID)
    assert third is not first
