# AGENTS.md — Profile RAG Agent

Cross-session notes for coding agents working in this repo.

## What this is

**Profile RAG Agent** — open-source RAG system for conversational profile discovery. Self-hosted / Hugging Face Spaces. Candidate configures profile sources + own LLM API key; recruiters open a public chat link.

## Quick map

| Path | Role |
|------|------|
| `backend/app/` | FastAPI RAG API |
| `frontend/src/` | Builder + chat UI |
| `Dockerfile` | Production/Spaces image |
| `docker-compose.yml` | Local run (`backend` bind-mounted; UI from image dist) |
| `examples/sample-profile/` | Smoke-test corpus |
| `.env` | Secrets (gitignored); escape `$` as `$$` for Compose |

## Do / don’t

- **Do** keep RAG grounded; prefer fix retrieval/ingest over loosening the system prompt into hallucination.
- **Do** rebuild Docker after frontend changes.
- **Do** remind users to reindex/recreate agents after embed/chunk/PDF pipeline changes.
- **Don’t** add LinkedIn scraping or commit secrets.
- **Don’t** reintroduce exclusive accordion unmount or `disabled={busy}` on the chat input.

## Deeper rules

See `.cursor/rules/project-overview.mdc`, `backend-rag.mdc`, and `frontend-ui.mdc`.
