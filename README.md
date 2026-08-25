# Profile RAG Agent

**Open-source RAG system for conversational profile discovery.**

Candidates ingest a resume, pasted LinkedIn/FAQ text, GitHub, and notes into a grounded retrieval pipeline, deploy once (local Docker or a free VM), and share a public chat URL with recruiters. Recruiters never install anything. Answers stay tied to uploaded sources — unknowns are refused, not invented.

**Live demo (this author's profile):** [https://chat.rdhumal.com/a/5d0805be2236](https://chat.rdhumal.com/a/5d0805be2236)

## Features

- **Hybrid grounded RAG chat** — dense (Chroma) + BM25 lexical search, fused with reciprocal rank fusion, reranked by a CPU cross-encoder, with follow-up query condensation for multi-turn chat
- **Multi-source ingest** — PDF/Markdown resume, pasted LinkedIn & Scholar text, FAQ fields, blog notes, public GitHub
- **Local embeddings** — FastEmbed ONNX (`all-MiniLM-L6-v2`) + CPU cross-encoder reranker (`ms-marco-MiniLM-L-6-v2`); no GPU or PyTorch required
- **BYO LLM** — OpenAI-compatible clients for NVIDIA NIM, Groq, or Ollama
- **Owner-gated builder** — `OWNER_SECRET` protects create/reindex; public chat is shareable
- **Measured, not vibes-tuned** — a golden-set retrieval eval (`evals/`) gates recall/MRR regressions in CI; see [docs/EVALUATION.md](docs/EVALUATION.md)
- **Hardened for public chat** — per-client + per-agent rate limiting, request-ID structured logs, safe (non-blanking) reindex, path-traversal-safe static serving
- **Self-host deploy** — single Docker image; Oracle Always Free + Cloudflare Tunnel recommended for a public HTTPS URL

## Stack

| Layer | Choice |
|-------|--------|
| API | FastAPI (`backend/app/`) |
| UI | React + Vite (`frontend/`) |
| Embeddings | FastEmbed (ONNX) |
| Vector store | Chroma on disk |
| LLM | OpenAI-compatible HTTP API |
| Deploy | Docker Compose (local) / Oracle Always Free + Cloudflare Tunnel |

## System architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  Candidate (builder UI)          Recruiter (public chat)    │
│  /  + OWNER_SECRET               /a/<agent_id>              │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐    ┌─────────────────────────────┐
│  Ingest pipeline         │    │  Chat / hybrid RAG          │
│  · PDF → text (PyMuPDF)  │    │  · rate limit → condense    │
│  · GitHub API (split docs)│   │  · dense + BM25 + intent    │
│  · FAQ / paste sources   │    │  · RRF fuse → CPU rerank    │
│  · markdown-aware chunks │    │  · grounded system prompt   │
│  · atomic reindex swap   │    │  · LLM (NVIDIA/Groq/Ollama) │
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

**Request path (chat):** rate limit (per-client + per-agent daily cap) → condense follow-up questions using recent history → dense (Chroma) + BM25 + intent-filtered dense queries → reciprocal rank fusion → CPU cross-encoder rerank → relevance gate → context budget → LLM → grounded reply. See [docs/EVALUATION.md](docs/EVALUATION.md) for how retrieval quality is measured.

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

## Deploy on Oracle Always Free

Recommended free public host: an [Oracle Cloud Always Free](https://www.oracle.com/cloud/free/) Ubuntu VM plus a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) for HTTPS. The tunnel reaches `localhost:7860` — **do not** open ingress port 7860 on the Oracle security list.

A tunnel is not strictly required (you can open TCP 7860 for a test), but it is the practical way to get a stable `https://chat.<your-domain>/a/<agent_id>` recruiter link. You need a domain you control on Cloudflare (`*.github.io` cannot be a tunnel hostname). A subdomain such as `chat.` can host the agent; keep the apex for a portfolio later.

**Full walkthrough (VCN, SSH, apt mirrors, Cloudflare Routes):** [docs/ORACLE_DEPLOY.md](docs/ORACLE_DEPLOY.md)

```text
Recruiter → HTTPS (Cloudflare) → Tunnel → VM → Docker app :7860 → ./data
```

### Quick path

```bash
ssh ubuntu@<VM_PUBLIC_IP>
git clone https://github.com/<you>/profile-rag-agent.git   # or -b deploy/oracle
cd profile-rag-agent
bash scripts/oracle-bootstrap.sh   # first run creates .env — edit it, then re-run
# Set LLM_API_KEY, OWNER_SECRET (escape $ as $$), PUBLIC_CHAT_ONLY=true
bash scripts/oracle-bootstrap.sh
curl -s http://127.0.0.1:7860/api/health
```

Then: named Cloudflare tunnel (Ubuntu ARM → **Debian** + **arm64**), **Routes → Add route → Published application**, hostname e.g. `chat.example.com` → **HTTP** `http://localhost:7860`. Unlock the builder, create an agent, share **only** `/a/<agent_id>` (incognito check). Do not share `OWNER_SECRET`.

### Updates and troubleshooting

- After UI or Dockerfile changes: `git pull` then `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- After PDF/chunk/GitHub pipeline changes: recreate the agent or `POST /api/agents/{id}/reindex` with the owner header
- `Invalid or missing owner secret`: escape `$` as `$$` in `.env`, recreate containers, unlock with the literal secret (one `$`)
- SSH timeout: missing Internet Gateway or public route table — see the deploy guide
- `Could not resolve iad-ad-*.clouds.ports.ubuntu.com`: switch apt to `ports.ubuntu.com` (Ampere Ubuntu)
- See [docs/ORACLE_DEPLOY.md](docs/ORACLE_DEPLOY.md) for VCN/route-table gotchas, Cloudflare UI, checklist, and troubleshooting

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

## Testing & evaluation

```bash
cd backend
pip install -r requirements-dev.txt
cd ..
ruff check backend evals scripts   # lint
pytest -q                          # unit + API tests (isolated temp DATA_DIR, no LLM calls)
python evals/run_eval.py           # retrieval golden-set eval (recall/MRR vs. baseline)
```

All three run in CI (`.github/workflows/ci.yml`) on every pull request, along
with a Docker build check. The retrieval eval needs no `LLM_API_KEY` — only
the embedding and reranker ONNX models, downloaded anonymously from Hugging
Face. See [docs/EVALUATION.md](docs/EVALUATION.md) for what it measures and
how to extend the golden set.

## Security

- Never commit `.env`, Cloudflare tunnel tokens, or put `LLM_API_KEY` in the frontend.
- On public VMs set `PUBLIC_CHAT_ONLY=true` (prod Compose sets this) so only owners with `OWNER_SECRET` can create/reindex.
- Mutating routes require `X-Owner-Secret` when `OWNER_SECRET` is set. Use a strong secret; escape `$` as `$$` in Compose `.env` files.
- Set `ALLOWED_ORIGINS` to your real chat domain(s) in production; the `*` default never combines with credentialed CORS.
- `/api/chat` is rate-limited per client (in-process token bucket; reads `CF-Connecting-IP` behind the tunnel) plus a per-agent daily cap (`RATE_LIMIT_*`, `AGENT_DAILY_CHAT_LIMIT`) — tune these before publicizing a link.
- Prefer Cloudflare Tunnel over exposing `0.0.0.0:7860` on the public internet (no ingress port needed).
- Free NIM tiers are rate-limited; fine for personal recruiting traffic, not a public viral bot.
- `/api/metrics` (basic request-count/latency counters) is owner-gated like the builder routes.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
