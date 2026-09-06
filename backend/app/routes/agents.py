from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth import require_owner
from app.ingest import build_source_corpus, index_corpus
from app.schemas import AgentCreateFields, AgentMeta, FaqAnswers
from app.store import create_agent_id, list_agents, load_meta, save_meta, sources_dir, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])


def _parse_faq(raw: str | None) -> FaqAnswers:
    if not raw:
        return FaqAnswers()
    try:
        return FaqAnswers.model_validate(json.loads(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid faq JSON: {exc}") from exc


@router.get("")
def get_agents() -> list[AgentMeta]:
    return list_agents()


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> AgentMeta:
    try:
        return load_meta(agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", dependencies=[Depends(require_owner)])
async def create_agent(
    display_name: Annotated[str, Form()],
    headline: Annotated[str, Form()] = "",
    linkedin_url: Annotated[str, Form()] = "",
    linkedin_text: Annotated[str, Form()] = "",
    github_username: Annotated[str, Form()] = "",
    scholar_url: Annotated[str, Form()] = "",
    scholar_text: Annotated[str, Form()] = "",
    blog_text: Annotated[str, Form()] = "",
    faq: Annotated[str | None, Form()] = None,
    resume: UploadFile | None = File(default=None),
) -> AgentMeta:
    display_name = display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")

    fields = AgentCreateFields(
        display_name=display_name,
        headline=headline.strip(),
        linkedin_url=linkedin_url.strip(),
        linkedin_text=linkedin_text,
        github_username=github_username.strip(),
        scholar_url=scholar_url.strip(),
        scholar_text=scholar_text,
        blog_text=blog_text,
        faq=_parse_faq(faq),
    )

    resume_bytes: bytes | None = None
    resume_filename: str | None = None
    if resume is not None and resume.filename:
        resume_bytes = await resume.read()
        resume_filename = resume.filename
        if len(resume_bytes) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Resume must be under 8MB")

    agent_id = create_agent_id()
    now = utc_now()
    try:
        corpus = build_source_corpus(agent_id, fields, resume_bytes, resume_filename)
        chunk_count = index_corpus(agent_id, corpus)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to create agent")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    meta = AgentMeta(
        id=agent_id,
        display_name=fields.display_name,
        headline=fields.headline,
        linkedin_url=fields.linkedin_url,
        github_username=fields.github_username,
        scholar_url=fields.scholar_url,
        created_at=now,
        updated_at=now,
        source_count=len(corpus),
        chunk_count=chunk_count,
    )
    save_meta(meta)
    return meta


@router.post("/{agent_id}/reindex", dependencies=[Depends(require_owner)])
def reindex_agent(agent_id: str) -> AgentMeta:
    try:
        meta = load_meta(agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    from app.pdf_extract import extract_pdf_text
    from app.store import write_source_file

    src_dir = sources_dir(agent_id)
    corpus: list[tuple[str, str]] = []
    saw_pdf = False

    for path in sorted(src_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            saw_pdf = True
            try:
                text = extract_pdf_text(path.read_bytes())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            write_source_file(agent_id, "resume_extracted.md", f"# Resume\n\n{text}\n")
            corpus.append(("resume_extracted.md", text))
        elif path.suffix.lower() in {".md", ".txt", ".json"}:
            if path.name == "resume_extracted.md":
                # Prefer freshly extracted text from PDF when present
                continue
            corpus.append((path.name, path.read_text(encoding="utf-8", errors="ignore")))

    extracted = src_dir / "resume_extracted.md"
    if not saw_pdf and extracted.exists():
        corpus.insert(0, ("resume_extracted.md", extracted.read_text(encoding="utf-8", errors="ignore")))

    chunk_count = index_corpus(agent_id, corpus)
    meta.chunk_count = chunk_count
    meta.source_count = len(corpus)
    meta.updated_at = utc_now()
    save_meta(meta)
    return meta
