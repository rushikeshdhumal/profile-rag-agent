---
title: Profile RAG Agent
emoji: 💬
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Profile RAG Agent

**Open-source RAG system for conversational profile discovery.**

Candidates ingest a resume, pasted LinkedIn/FAQ text, GitHub, and notes into a grounded retrieval pipeline, deploy once (locally or on Hugging Face Spaces), and share a public chat URL with recruiters. Recruiters never install anything. Answers stay tied to uploaded sources — unknowns are refused, not invented.

## Features

- **Grounded RAG chat** — retrieval-augmented answers with source-aware boosting (resume, FAQ, GitHub)
- **Multi-source ingest** — PDF/Markdown resume, pasted LinkedIn & Scholar text, FAQ fields, blog notes, public GitHub
- **Local embeddings** — FastEmbed ONNX (`all-MiniLM-L6-v2`); no GPU or PyTorch required
- **BYO LLM** — OpenAI-compatible clients for NVIDIA NIM, Groq, or Ollama
- **Owner-gated builder** — `OWNER_SECRET` protects create/reindex; public chat is shareable
- **Free deploy path** — single Docker image for local Compose or Hugging Face Spaces

## Stack

| Layer | Choice |
|-------|--------|
| API | FastAPI (`backend/app/`) |
| UI | React + Vite (`frontend/`) |
| Embeddings | FastEmbed (ONNX) |
| Vector store | Chroma on disk |
| LLM | OpenAI-compatible HTTP API |
| Deploy | Docker / Docker Compose / HF Spaces |

## System architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  Candidate (builder UI)          Recruiter (public chat)    │
│  /  + OWNER_SECRET               /a/<agent_id>              │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐    ┌─────────────────────────────┐
│  Ingest pipeline         │    │  Chat / RAG                 │
│  · PDF → text (PyMuPDF)  │    │  · query → embed            │
│  · GitHub API (split docs)│   │  · Chroma retrieval + boost │
│  · FAQ / paste sources   │    │  · grounded system prompt   │
│  · markdown-aware chunks │    │  · LLM (NVIDIA/Groq/Ollama) │
└──────────────┬───────────┘    └──────────────▲──────────────┘
               │                               │
               ▼                               │
┌──────────────────────────┐                   │
│  data/agents/<id>/       │───────────────────┘
│  · sources/              │
│  · chroma/               │
│  · meta.json             │
└──────────────────────────┘
```

**Request path (chat):** message → embed → Chroma top-k (distance cutoff ~0.88) → query-type boosts (experience → resume/LinkedIn; logistics → FAQ; projects → GitHub) → context budget → LLM → grounded reply.

**Data layout:** each agent is a folder on disk — no paid database. The API serves the built frontend from `frontend/dist` in production.

## Quick start

### Prerequisites

- Docker and Docker Compose
- An LLM API key ([NVIDIA NIM](https://build.nvidia.com/), [Groq](https://console.groq.com/), or local Ollama)

### Local (Docker)

```bash
cp .env.example .env
# Set LLM_API_KEY and OWNER_SECRET
# If OWNER_SECRET contains `$`, write each `$` as `$$` in .env (Compose interpolation)

docker compose up --build
```

Open [http://localhost:7860](http://localhost:7860), unlock with your `OWNER_SECRET` (literal `$`, not `$$`), create an agent, then share `/a/<agent_id>`.

If create returns `Invalid or missing owner secret`:

1. Escape `$` as `$$` in `.env`
2. `docker compose down` then `docker compose up --build`
3. Hard-refresh the browser and unlock with the literal secret

### Dev without Docker

```bash
# API
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cd ..
# set DATA_DIR=./data (or export it)
uvicorn app.main:app --app-dir backend --reload --port 7860

# UI (second terminal)
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to port 7860.

## Deploy (Hugging Face Spaces)

1. Create a **Docker** Space and push this repo (or connect GitHub).
2. **Secrets:** `LLM_API_KEY`, `OWNER_SECRET`; optional `GITHUB_TOKEN`, `LLM_*` overrides.
3. **Variables:** `PUBLIC_CHAT_ONLY=true`, plus `LLM_PROVIDER` / `LLM_MODEL` as needed.
4. Unlock the builder with `OWNER_SECRET`, create an agent, share the chat URL.

Custom domain: Cloudflare CNAME → [HF Spaces custom domains](https://huggingface.co/docs/hub/spaces-config-reference). Free Spaces may cold-start (~30–60s after idle).

## Ingestion sources

| Source | How |
|--------|-----|
| Resume | Upload PDF or Markdown (PDF → PyMuPDF, pypdf fallback → `resume_extracted.md`) |
| LinkedIn | Paste About/Experience (URL stored as metadata; no scraping) |
| FAQ | Form fields (relocate, visa, roles, …) |
| Blog / notes | Paste Markdown |
| GitHub | Optional username → public API (identity, repos, truncated READMEs as separate docs) |
| Google Scholar | Paste publications list |

After PDF, chunking, or GitHub pipeline changes, **re-create the agent** or `POST /api/agents/{id}/reindex` with the owner header.

## LLM providers

**NVIDIA NIM**

```env
LLM_PROVIDER=NVIDIA
LLM_API_KEY=nvapi-...
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=meta/llama-3.1-8b-instruct
```

**Groq**

```env
LLM_PROVIDER=GROQ
LLM_API_KEY=gsk_...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-8b-instant
```

**Ollama (local)**

```env
LLM_PROVIDER=OLLAMA
LLM_API_KEY=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1
```

## Smoke test

1. Start with a valid `LLM_API_KEY`.
2. Use `examples/sample-profile/` (display name + `resume.md` + FAQ from `profile.json`).
3. Create agent → open chat.
4. “Are you open to relocate?” → should hit FAQ.
5. “What is your favorite color?” → should refuse / say not in profile.

## Security

- Never commit `.env` or put `LLM_API_KEY` in the frontend.
- Mutating routes require `X-Owner-Secret` when `OWNER_SECRET` is set.
- Free NIM tiers are rate-limited; fine for personal recruiting traffic, not a public viral bot.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
