# AGENTS.md — Profile RAG Agent

Cross-session notes for coding agents working in this repo.

## What this is

**Profile RAG Agent** — open-source RAG system for conversational profile discovery. Self-hosted (Docker / Oracle Always Free + Cloudflare Tunnel). Candidate configures profile sources + own LLM API key; recruiters open a public chat link.

**Tagline:** Open-source RAG system for conversational profile discovery.

## Status (2026-08-24)

Live recruiter chat (author's profile): https://chat.rdhumal.com/a/5d0805be2236

- **Git:** deploy work is on **`main`** (merge PR `#1`, commit `2bc3018` — Oracle deploy docs/compose). Feature branch `deploy/oracle` is obsolete; VM should `checkout main` + `pull` before that branch is deleted.
- **Public host:** Oracle Always Free `VM.Standard.A1.Flex` (1 OCPU / 6 GB, Ubuntu 22.04 **aarch64**), VCN `profile-rag-vcn`, Cloudflare named tunnel, published app **`chat.rdhumal.com` → `http://localhost:7860`**. Do not open ingress 7860.
- **Prod run on VM:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` (`PUBLIC_CHAT_ONLY=true`, no backend bind-mount). Local `docker compose up` still uses `docker-compose.override.yml`.
- **Image vs git:** Dockerfile copies backend/frontend/examples only. A docs-only `main` merge cache-hits the image; running chat is fine without a layer rebuild. Rebuild after backend/frontend/Dockerfile changes.
- **Not used:** Hugging Face Spaces (Docker/Gradio paid; Static cannot run this API). GitHub Pages cannot be the tunnel hostname.
- **Optional later:** apex `rdhumal.com` for a static portfolio; keep `chat.` for the agent.

Full Oracle/VCN/Cloudflare gotchas: `docs/ORACLE_DEPLOY.md`.

## Quick map

| Path | Role |
|------|------|
| `backend/app/` | FastAPI RAG API |
| `frontend/src/` | Builder + chat UI |
| `Dockerfile` | Production image |
| `docker-compose.yml` | Base Compose (`./data` volume) |
| `docker-compose.override.yml` | Local only: bind-mounts `./backend` |
| `docker-compose.prod.yml` | Oracle/public: `PUBLIC_CHAT_ONLY`, no backend mount |
| `scripts/oracle-bootstrap.sh` | VM Docker install + prod `up --build` |
| `docs/ORACLE_DEPLOY.md` | Full Oracle + Cloudflare Tunnel walkthrough (VCN, apt mirrors, Routes UI) |
| `examples/sample-profile/` | Smoke-test corpus |
| `.env` | Secrets (gitignored); escape `$` as `$$` for Compose |

## Do / don’t

- **Do** keep RAG grounded; prefer fix retrieval/ingest over loosening the system prompt into hallucination.
- **Do** rebuild Docker after frontend changes.
- **Do** remind users to reindex/recreate agents after embed/chunk/PDF pipeline changes.
- **Don’t** add LinkedIn scraping or commit secrets (`.env`, tunnel tokens).
- **Don’t** reintroduce exclusive accordion unmount or `disabled={busy}` on the chat input.

## Deeper rules

See `.cursor/rules/project-overview.mdc`, `backend-rag.mdc`, and `frontend-ui.mdc`.
