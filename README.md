# Profile RAG Agent

**Open-source RAG system for conversational profile discovery.**

Candidates ingest a resume, pasted LinkedIn/FAQ text, GitHub, and notes into a grounded retrieval pipeline, deploy once (local Docker or a free VM), and share a public chat URL with recruiters. Recruiters never install anything. Answers stay tied to uploaded sources — unknowns are refused, not invented.

## Features

- **Grounded RAG chat** — retrieval-augmented answers with source-aware boosting (resume, FAQ, GitHub)
- **Multi-source ingest** — PDF/Markdown resume, pasted LinkedIn & Scholar text, FAQ fields, blog notes, public GitHub
- **Local embeddings** — FastEmbed ONNX (`all-MiniLM-L6-v2`); no GPU or PyTorch required
- **BYO LLM** — OpenAI-compatible clients for NVIDIA NIM, Groq, or Ollama
- **Owner-gated builder** — `OWNER_SECRET` protects create/reindex; public chat is shareable
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

## Deploy on Oracle Always Free

Recommended free public host: an [Oracle Cloud Always Free](https://www.oracle.com/cloud/free/) Ubuntu VM plus a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) for HTTPS. The tunnel reaches `localhost:7860` — **do not** open ingress port 7860 on the Oracle security list.

```text
Recruiter → HTTPS (Cloudflare) → Tunnel → VM → Docker app :7860 → ./data
```

### 1. Create the VM

1. In Oracle Cloud, create an Always Free **Ubuntu** instance (ARM Ampere if available; x86 also fine).
2. Attach your SSH public key; note the public IP for SSH only.
3. Ensure the VM can reach the internet outbound (pull Docker images, call NIM/Groq).

### 2. Install Docker and clone

```bash
ssh ubuntu@<VM_PUBLIC_IP>
git clone https://github.com/<you>/profile-rag-agent.git
cd profile-rag-agent
bash scripts/oracle-bootstrap.sh   # installs Docker if needed; copies .env.example on first run
```

### 3. Configure `.env` on the VM

```bash
nano .env   # or vim
```

Set at least:

- `LLM_API_KEY` (and provider/model if not using the NVIDIA defaults)
- `OWNER_SECRET` — strong random string; if it contains `$`, write each `$` as `$$` (Compose interpolation)
- `PUBLIC_CHAT_ONLY=true` (also forced by [`docker-compose.prod.yml`](docker-compose.prod.yml))

Then start (or re-run the bootstrap script):

```bash
bash scripts/oracle-bootstrap.sh
# equivalent:
# docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Production compose uses the image build only (no `./backend` bind-mount). Local `docker compose up` still mounts backend via [`docker-compose.override.yml`](docker-compose.override.yml).

Health check on the VM:

```bash
curl -s http://127.0.0.1:7860/api/health
```

### 4. Cloudflare Tunnel (public HTTPS)

1. Create a Cloudflare account; add a site or use a `*.trycloudflare.com` quick tunnel for a trial.
2. On the VM, install [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).
3. Create a **named tunnel** and a public hostname that routes to `http://localhost:7860`.
4. Install the tunnel as a service with your token (`cloudflared service install <TOKEN>`). **Never commit the token.**

After the tunnel is up, open the Cloudflare hostname, unlock the builder with `OWNER_SECRET`, create an agent, and share `https://<your-host>/a/<agent_id>`.

### 5. Updates and troubleshooting

- After UI or Dockerfile changes: `git pull` then `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- After PDF/chunk/GitHub pipeline changes: recreate the agent or `POST /api/agents/{id}/reindex` with the owner header
- `Invalid or missing owner secret`: escape `$` as `$$` in `.env`, recreate containers, unlock with the literal secret (one `$`)

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

- Never commit `.env`, Cloudflare tunnel tokens, or put `LLM_API_KEY` in the frontend.
- On public VMs set `PUBLIC_CHAT_ONLY=true` (prod Compose sets this) so only owners with `OWNER_SECRET` can create/reindex.
- Mutating routes require `X-Owner-Secret` when `OWNER_SECRET` is set. Use a strong secret; escape `$` as `$$` in Compose `.env` files.
- Prefer Cloudflare Tunnel over exposing `0.0.0.0:7860` on the public internet (no ingress port needed).
- Free NIM tiers are rate-limited; fine for personal recruiting traffic, not a public viral bot.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
