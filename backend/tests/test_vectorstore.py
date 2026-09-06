from __future__ import annotations

from app.vectorstore import (
    fetch_all_chunks,
    fetch_chunks_by_source_type,
    get_collection,
    query_chunks,
    replace_collection,
)

AGENT_ID = "vs-test-agent"


def _seed(agent_id: str = AGENT_ID) -> None:
    ids = ["a1", "a2", "a3"]
    documents = [
        "Ada is a Senior ML Engineer at Northwind Labs.",
        "Ada is open to relocating to the US and Canada.",
        "Ada built the rag-toolkit GitHub repository.",
    ]
    metadatas = [
        {"source": "resume.md", "source_type": "resume", "index": 0, "heading": "", "char_start": 0},
        {"source": "faq_open_to_relocate.md", "source_type": "faq", "index": 0, "heading": "", "char_start": 0},
        {"source": "github_repo_rag_toolkit.md", "source_type": "github", "index": 0, "heading": "", "char_start": 0},
    ]
    replace_collection(agent_id, ids, documents, metadatas)


def test_replace_collection_indexes_documents():
    _seed()
    collection = get_collection(AGENT_ID)
    assert collection.count() == 3


def test_replace_collection_is_idempotent_and_swaps_cleanly():
    _seed("vs-test-swap")
    # Re-index with fewer documents; the old ones must not linger.
    replace_collection(
        "vs-test-swap",
        ["b1"],
        ["Ada's notice period is two weeks."],
        [{"source": "faq_notice_period.md", "source_type": "faq", "index": 0, "heading": "", "char_start": 0}],
    )
    collection = get_collection("vs-test-swap")
    assert collection.count() == 1


def test_query_chunks_returns_relevant_result():
    _seed("vs-test-query")
    results = query_chunks("vs-test-query", "Where does Ada work?", k=3)
    assert results
    assert any("Northwind" in r["text"] for r in results)


def test_query_chunks_empty_collection_returns_empty_list():
    assert query_chunks("vs-test-nonexistent-agent", "anything", k=3) == []


def test_fetch_chunks_by_source_type_uses_where_filter():
    _seed("vs-test-filter")
    faq_chunks = fetch_chunks_by_source_type("vs-test-filter", "faq", limit=10)
    assert len(faq_chunks) == 1
    assert faq_chunks[0]["source"] == "faq_open_to_relocate.md"

    resume_chunks = fetch_chunks_by_source_type("vs-test-filter", "resume", limit=10)
    assert len(resume_chunks) == 1
    assert resume_chunks[0]["source"] == "resume.md"


def test_fetch_chunks_by_source_type_supports_multiple_types():
    _seed("vs-test-filter-multi")
    chunks = fetch_chunks_by_source_type("vs-test-filter-multi", ["resume", "github"], limit=10)
    sources = {c["source"] for c in chunks}
    assert sources == {"resume.md", "github_repo_rag_toolkit.md"}


def test_fetch_all_chunks_returns_full_corpus():
    _seed("vs-test-all")
    chunks = fetch_all_chunks("vs-test-all")
    assert len(chunks) == 3
