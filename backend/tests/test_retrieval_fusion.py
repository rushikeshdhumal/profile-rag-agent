from __future__ import annotations

from app.retrieval import (
    EXPERIENCE_SOURCE_TYPES,
    GITHUB_SOURCE_TYPES,
    LOGISTICS_SOURCE_TYPES,
    _intent_source_types,
    _rrf_fuse,
)


def test_intent_source_types_experience_wins_over_github():
    # "projects" alone would look like a GitHub query, but "experience" should win
    types = _intent_source_types("Tell me about her work experience and projects")
    assert types == EXPERIENCE_SOURCE_TYPES


def test_intent_source_types_logistics():
    assert _intent_source_types("Is she open to relocating?") == LOGISTICS_SOURCE_TYPES


def test_intent_source_types_github():
    assert _intent_source_types("What repos has she built?") == GITHUB_SOURCE_TYPES


def test_intent_source_types_none_for_generic_question():
    assert _intent_source_types("Hello there!") is None


def test_rrf_fuse_promotes_chunk_ranked_high_in_multiple_lists():
    shared = {"source": "resume.md", "text": "Ada works at Northwind Labs."}
    only_in_dense = {"source": "blog_notes.md", "text": "Recruiters need facts."}
    only_in_bm25 = {"source": "faq_notice_period.md", "text": "Two weeks notice."}

    dense = [shared, only_in_dense]
    bm25 = [shared, only_in_bm25]

    fused = _rrf_fuse([(dense, 1.0), (bm25, 0.7)])

    assert fused[0]["source"] == "resume.md"
    sources = [c["source"] for c in fused]
    assert set(sources) == {"resume.md", "blog_notes.md", "faq_notice_period.md"}


def test_rrf_fuse_deduplicates_by_source_and_text_prefix():
    chunk = {"source": "resume.md", "text": "Ada works at Northwind Labs."}
    fused = _rrf_fuse([([chunk], 1.0), ([dict(chunk)], 0.7)])
    assert len(fused) == 1


def test_rrf_fuse_empty_lists_returns_empty():
    assert _rrf_fuse([([], 1.0), ([], 0.7)]) == []
