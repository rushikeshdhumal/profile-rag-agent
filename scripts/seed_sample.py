"""Create an agent from examples/sample-profile without the UI (for smoke tests)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest import build_source_corpus, index_corpus  # noqa: E402
from app.schemas import AgentCreateFields, FaqAnswers  # noqa: E402
from app.store import create_agent_id, save_meta, utc_now  # noqa: E402
from app.schemas import AgentMeta  # noqa: E402


def main() -> None:
    sample = ROOT / "examples" / "sample-profile"
    payload = json.loads((sample / "profile.json").read_text(encoding="utf-8"))
    resume = (sample / "resume.md").read_bytes()
    fields = AgentCreateFields(
        display_name=payload["display_name"],
        headline=payload.get("headline", ""),
        linkedin_url=payload.get("linkedin_url", ""),
        linkedin_text=payload.get("linkedin_text", ""),
        github_username=payload.get("github_username", ""),
        scholar_url=payload.get("scholar_url", ""),
        scholar_text=payload.get("scholar_text", ""),
        blog_text=payload.get("blog_text", ""),
        faq=FaqAnswers.model_validate(payload.get("faq", {})),
    )
    agent_id = create_agent_id()
    corpus = build_source_corpus(agent_id, fields, resume, "resume.md")
    chunks = index_corpus(agent_id, corpus)
    now = utc_now()
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
        chunk_count=chunks,
    )
    save_meta(meta)
    print(f"Created agent {agent_id} with {chunks} chunks")
    print(f"Chat path: /a/{agent_id}")


if __name__ == "__main__":
    main()
