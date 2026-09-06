"""Deterministic, offline corpus for retrieval evaluation.

Mirrors examples/sample-profile (same display name, resume, LinkedIn/blog/
scholar paste, FAQ) plus a few synthetic GitHub documents, so the golden set
can cover every source_type category without any network call or secret.
Real GitHub ingestion (app.github_fetch) hits the live API and is
intentionally not used here.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "examples" / "sample-profile"

GITHUB_USERNAME = "ada-example"

_GITHUB_IDENTITY = f"""# GitHub profile
Login: {GITHUB_USERNAME}
Name: Ada Example
Bio: ML engineer building grounded RAG systems.
Company: Northwind Labs
Location: Toronto, Canada
Public repos: 12
Followers: 84
Profile URL: https://github.com/{GITHUB_USERNAME}
"""

# rag-toolkit is given a strictly later "updated" than eval-harness so a
# "most recent GitHub project" question has one unique correct answer.
_GITHUB_REPOS = """# Recent public repositories (most recently updated first)
- rag-toolkit: A hybrid retrieval toolkit combining BM25 and dense search. (language=Python, stars=142, updated=2026-08-18, pushed=2026-08-18, url=https://github.com/ada-example/rag-toolkit)
- eval-harness: Golden-set evaluation harness for RAG pipelines. (language=Python, stars=37, updated=2026-01-02, pushed=2026-01-02, url=https://github.com/ada-example/eval-harness)
"""

_GITHUB_REPO_RAGTOOLKIT = """# Repository: rag-toolkit

URL: https://github.com/ada-example/rag-toolkit
Language: Python
Stars: 142
Updated: 2026-08-18
Pushed: 2026-08-18
Description: A hybrid retrieval toolkit combining BM25 and dense search.

## What it does

rag-toolkit fuses BM25 lexical search with dense vector retrieval using
reciprocal rank fusion, then reranks candidates with a cross-encoder.

## Stack

Python, FastAPI, Chroma, ONNX Runtime.
"""


def _faq_docs(faq: dict) -> list[tuple[str, str]]:
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
    for key, label in mapping.items():
        value = (faq.get(key) or "").strip()
        if value:
            docs.append((f"faq_{key}.md", f"# FAQ: {label}\n\n{value}\n"))
    return docs


def build_eval_corpus() -> list[tuple[str, str]]:
    """Return (filename, text) pairs shaped like app.ingest.build_source_corpus."""
    payload = json.loads((SAMPLE_DIR / "profile.json").read_text(encoding="utf-8"))
    corpus: list[tuple[str, str]] = []

    resume_text = (SAMPLE_DIR / "resume.md").read_text(encoding="utf-8")
    corpus.append(("resume.md", resume_text))

    linkedin_text = payload.get("linkedin_text", "").strip()
    if linkedin_text:
        corpus.append(
            (
                "linkedin_paste.md",
                f"# LinkedIn profile (pasted)\n\nURL: {payload.get('linkedin_url', '')}\n\n{linkedin_text}\n",
            )
        )

    blog_text = payload.get("blog_text", "").strip()
    if blog_text:
        corpus.append(("blog_notes.md", f"# Blog / notes\n\n{blog_text}\n"))

    scholar_text = payload.get("scholar_text", "").strip()
    if scholar_text:
        corpus.append(
            (
                "scholar_paste.md",
                f"# Google Scholar (pasted)\n\nURL: {payload.get('scholar_url', '')}\n\n{scholar_text}\n",
            )
        )

    corpus.extend(_faq_docs(payload.get("faq", {})))

    corpus.append(("github_identity.md", _GITHUB_IDENTITY))
    corpus.append(("github_repos.md", _GITHUB_REPOS))
    corpus.append(("github_repo_rag_toolkit.md", _GITHUB_REPO_RAGTOOLKIT))

    identity = (
        f"# Candidate identity\n\n"
        f"Name: {payload['display_name']}\n"
        f"Headline: {payload.get('headline', '')}\n"
        f"LinkedIn: {payload.get('linkedin_url', '')}\n"
        f"GitHub: {GITHUB_USERNAME}\n"
        f"Scholar: {payload.get('scholar_url', '')}\n"
    )
    corpus.append(("identity.md", identity))

    return corpus


def build_eval_agent(agent_id: str) -> None:
    """Index the eval corpus for `agent_id` under whatever DATA_DIR is active."""
    from app.ingest import index_corpus

    index_corpus(agent_id, build_eval_corpus())
