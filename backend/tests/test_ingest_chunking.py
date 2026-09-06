from __future__ import annotations

from app.ingest import CHUNK_SIZE, chunk_text, source_type_for


def test_source_type_for_prefixes():
    assert source_type_for("resume_extracted.md") == "resume"
    assert source_type_for("my_resume.pdf") == "resume"
    assert source_type_for("faq_notice_period.md") == "faq"
    assert source_type_for("github_repo_foo.md") == "github"
    assert source_type_for("linkedin_paste.md") == "linkedin"
    assert source_type_for("identity.md") == "identity"
    assert source_type_for("blog_notes.md") == "blog"
    assert source_type_for("random.md") == "other"


def test_chunk_text_empty():
    assert chunk_text("", "resume.md") == []
    assert chunk_text("   \n  ", "resume.md") == []


def test_chunk_text_does_not_truncate_long_blocks():
    # A single paragraph much longer than CHUNK_SIZE must be fully preserved
    # across chunks, not silently cut off (the old MAX_CHUNK_CHARS bug).
    long_paragraph = "word " * 400  # ~2000 chars, no blank lines to split on
    chunks = chunk_text(long_paragraph, "resume.md")

    assert len(chunks) > 1
    reconstructed_len = sum(len(c["text"].strip()) for c in chunks)
    assert reconstructed_len >= len(long_paragraph.strip()) - CHUNK_SIZE  # allow for overlap trimming
    # every chunk must fit comfortably within the target size
    for c in chunks:
        assert len(c["text"]) <= CHUNK_SIZE + 50


def test_chunk_text_attaches_heading_breadcrumb():
    text = "# Experience\n\n## Senior ML Engineer\n\nBuilt grounded RAG systems.\n"
    chunks = chunk_text(text, "resume.md")

    assert len(chunks) == 1
    assert chunks[0]["heading"] == "Experience > Senior ML Engineer"
    assert "Experience > Senior ML Engineer" in chunks[0]["text"]
    assert "Built grounded RAG systems." in chunks[0]["text"]


def test_chunk_text_sets_source_metadata():
    chunks = chunk_text("# Summary\n\nSome text here.", "resume_extracted.md")
    assert chunks[0]["source"] == "resume_extracted.md"
    assert chunks[0]["source_type"] == "resume"
    assert chunks[0]["index"] == 0
    assert chunks[0]["char_start"] == 0


def test_chunk_text_multiple_paragraphs_get_increasing_char_start():
    text = "# Notes\n\nFirst paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text, "notes.md")
    assert len(chunks) == 3
    starts = [c["char_start"] for c in chunks]
    assert starts == sorted(starts)
    assert starts[0] < starts[1] < starts[2]
