# Contributing to Profile RAG Agent

Thanks for helping improve this project. Profile RAG Agent is an open-source, self-hosted RAG system for conversational profile discovery. Contributions should keep answers **grounded**, the deploy path **simple**, and the builder/chat UX **reliable**.

## Ways to contribute

- Bug reports and reproducible RAG quality issues
- Ingest / retrieval / PDF parsing improvements
- Docs, examples, and smoke-test coverage
- Accessible UI fixes that match the existing design

Out of scope unless discussed first: multi-tenant SaaS hosting, LinkedIn/Scholar scraping, fine-tuning pipelines, paid vector databases.

## Development setup

### Docker (recommended)

```bash
cp .env.example .env
# Set LLM_API_KEY and OWNER_SECRET
# Escape `$` as `$$` in OWNER_SECRET for Docker Compose

docker compose up --build
```

App: [http://localhost:7860](http://localhost:7860)

**Note:** Compose bind-mounts `backend/` only. After frontend changes, rebuild so `frontend/dist` updates:

```bash
docker compose up --build
```

### Local API + Vite

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cd ..
uvicorn app.main:app --app-dir backend --reload --port 7860

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to the API on port 7860.

## Project layout

| Path | Role |
|------|------|
| `backend/app/` | FastAPI: ingest, embeddings, Chroma, RAG chat |
| `frontend/src/` | Builder UI + public chat (`/a/:agentId`) |
| `examples/sample-profile/` | Smoke-test corpus |
| `Dockerfile` | Production image |
| `docker-compose.prod.yml` | Public VM / Oracle (`PUBLIC_CHAT_ONLY`, no backend mount) |
| `docker-compose.yml` | Local run |

Agent data lives under `data/agents/{id}/` (`meta.json`, `sources/`, `chroma/`). Do not commit secrets or personal agent data.

## Coding guidelines

### RAG / backend

- Prefer fixing retrieval, chunking, or ingest over loosening the system prompt into hallucination.
- Keep GitHub sources as **separate truncated docs** — do not re-merge into one giant blob.
- PDF path: PyMuPDF → pypdf fallback; persist cleaned text as `resume_extracted.md`.
- After embed/chunk/PDF pipeline changes, note that agents need **recreate or reindex**.
- Preserve Chroma telemetry safeguards (`posthog` pin, `anonymized_telemetry=False`).

### Frontend

- Accordion sections: keep panels mounted; use `hidden`, not conditional unmount (unmount clears form values).
- Chat input: do not disable the message field while a request is in flight; refocus after send.
- Match the existing minimal dark theme; avoid unrelated visual redesigns in bugfix PRs.

### Secrets & Compose

- Never commit `.env` or live API keys.
- In Compose `.env` files, escape `$` as `$$`. Do not remap `OWNER_SECRET` via `${OWNER_SECRET}` in `environment:` — Compose interpolation will eat `$VAR` segments.

## Pull requests

1. Fork and branch from the default branch.
2. Keep changes focused; one concern per PR when practical.
3. Update README / examples if behavior or setup changes.
4. Smoke-test with `examples/sample-profile/` when touching ingest or chat:
   - FAQ logistics question should retrieve FAQ sources
   - Off-profile trivia should be refused
5. Describe **what** changed and **why** (especially for retrieval thresholds or prompt changes).

## Reporting issues

Include:

- OS / Docker vs local-dev
- LLM provider and model (not the API key)
- Steps to reproduce
- Expected vs actual answer (for RAG bugs, note which sources were uploaded)
- Relevant container or API logs with secrets redacted

## License

By contributing, you agree that your contributions are licensed under the MIT License — see [LICENSE](LICENSE).
