from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from app.github_fetch import fetch_github_documents
from app.pdf_extract import MIN_RESUME_CHARS, extract_pdf_text
from app.schemas import AgentCreateFields, FaqAnswers
from app.store import write_source_file
from app.vectorstore import upsert_chunks

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 80
MAX_CHUNK_CHARS = 500


def source_type_for(filename: str) -> str:
    name = filename.lower()
    if name.startswith("faq_"):
        return "faq"
    if name.startswith("github_"):
        return "github"
    if name.startswith("linkedin"):
        return "linkedin"
    if name.startswith("blog"):
        return "blog"
    if name.startswith("scholar"):
        return "blog"
    if name.startswith("identity"):
        return "identity"
    if name.endswith(".pdf") or "resume" in name:
        return "resume"
    return "other"


def _split_markdown_blocks(text: str) -> list[str]:
    """Split on headings and blank lines before hard character cuts."""
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    # Keep heading lines attached to following content when possible
    parts = re.split(r"(?=\n#{1,6}\s)", text)
    blocks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        paragraphs = re.split(r"\n\s*\n", part)
        for para in paragraphs:
            para = para.strip()
            if para:
                blocks.append(para)
    return blocks or [text]


def chunk_text(text: str, source: str) -> list[dict[str, Any]]:
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []

    blocks = _split_markdown_blocks(text)
    chunks: list[dict[str, Any]] = []
    idx = 0
    source_type = source_type_for(source)

    for block in blocks:
        if len(block) <= CHUNK_SIZE:
            piece = block[:MAX_CHUNK_CHARS].strip()
            if piece:
                chunks.append(
                    {
                        "text": piece,
                        "source": source,
                        "source_type": source_type,
                        "index": idx,
                    }
                )
                idx += 1
            continue

        start = 0
        while start < len(block):
            end = min(len(block), start + CHUNK_SIZE)
            # Prefer breaking at whitespace near the end
            if end < len(block):
                window = block[start:end]
                br = max(window.rfind("\n"), window.rfind(" "))
                if br > CHUNK_SIZE // 3:
                    end = start + br
            piece = block[start:end].strip()[:MAX_CHUNK_CHARS]
            if piece:
                chunks.append(
                    {
                        "text": piece,
                        "source": source,
                        "source_type": source_type,
                        "index": idx,
                    }
                )
                idx += 1
            if end >= len(block):
                break
            start = max(0, end - CHUNK_OVERLAP)

    return chunks


def faq_to_documents(faq: FaqAnswers) -> list[tuple[str, str]]:
    mapping = {
        "open_to_relocate": "Open to relocate?",
        "work_authorization": "Work authorization / visa",
        "preferred_roles": "Preferred roles",
        "preferred_locations": "Preferred locations",
        "notice_period": "Notice period",
        "compensation_notes": "Compensation notes (optional)",
        "other": "Other FAQ",
    }
    docs: list[tuple[str, str]] = []
    data = faq.model_dump()
    for key, label in mapping.items():
        value = (data.get(key) or "").strip()
        if value:
            docs.append((f"faq_{key}.md", f"# FAQ: {label}\n\n{value}\n"))
    return docs


def build_source_corpus(
    agent_id: str,
    fields: AgentCreateFields,
    resume_bytes: bytes | None,
    resume_filename: str | None,
) -> list[tuple[str, str]]:
    """Persist source files and return (filename, text) pairs for indexing."""
    corpus: list[tuple[str, str]] = []

    if resume_bytes and resume_filename:
        name = resume_filename.lower()
        write_source_file(agent_id, resume_filename, resume_bytes)
        if name.endswith(".pdf"):
            text = extract_pdf_text(resume_bytes)
            # Persist cleaned text so reindex/debug don't depend on re-parsing the PDF
            write_source_file(agent_id, "resume_extracted.md", f"# Resume\n\n{text}\n")
            corpus.append(("resume_extracted.md", text))
        else:
            text = resume_bytes.decode("utf-8", errors="ignore").strip()
            if len(text) < MIN_RESUME_CHARS:
                raise ValueError(
                    "Resume file has too little text. Upload a PDF, Markdown, or TXT resume."
                )
            corpus.append((resume_filename, text))

    if fields.linkedin_text.strip():
        path = "linkedin_paste.md"
        body = f"# LinkedIn profile (pasted)\n\nURL: {fields.linkedin_url}\n\n{fields.linkedin_text.strip()}\n"
        write_source_file(agent_id, path, body)
        corpus.append((path, body))

    if fields.blog_text.strip():
        path = "blog_notes.md"
        body = f"# Blog / notes\n\n{fields.blog_text.strip()}\n"
        write_source_file(agent_id, path, body)
        corpus.append((path, body))

    if fields.scholar_text.strip():
        path = "scholar_paste.md"
        body = (
            f"# Google Scholar (pasted)\n\nURL: {fields.scholar_url}\n\n"
            f"{fields.scholar_text.strip()}\n"
        )
        write_source_file(agent_id, path, body)
        corpus.append((path, body))

    for filename, body in faq_to_documents(fields.faq):
        write_source_file(agent_id, filename, body)
        corpus.append((filename, body))

    if fields.github_username.strip():
        try:
            gh_docs = fetch_github_documents(fields.github_username)
            for path, body in gh_docs:
                write_source_file(agent_id, path, body)
                corpus.append((path, body))
        except Exception as exc:
            logger.warning("GitHub fetch failed: %s", exc)
            note = f"# GitHub fetch failed\n\nUsername: {fields.github_username}\nError: {exc}\n"
            write_source_file(agent_id, "github_fetch_error.md", note)
            corpus.append(("github_fetch_error.md", note))

    identity = (
        f"# Candidate identity\n\n"
        f"Name: {fields.display_name}\n"
        f"Headline: {fields.headline}\n"
        f"LinkedIn: {fields.linkedin_url}\n"
        f"GitHub: {fields.github_username}\n"
        f"Scholar: {fields.scholar_url}\n"
    )
    write_source_file(agent_id, "identity.md", identity)
    corpus.append(("identity.md", identity))

    return corpus


def index_corpus(agent_id: str, corpus: list[tuple[str, str]]) -> int:
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for source, text in corpus:
        for chunk in chunk_text(text, source):
            raw_id = f"{source}:{chunk['index']}:{chunk['text'][:40]}"
            chunk_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()
            ids.append(chunk_id)
            documents.append(chunk["text"])
            metadatas.append(
                {
                    "source": source,
                    "source_type": chunk["source_type"],
                    "index": chunk["index"],
                }
            )

    return upsert_chunks(agent_id, ids, documents, metadatas)
