# Oracle Always Free deployment guide

End-to-end steps to run Profile RAG Agent on an Oracle Cloud Always Free VM with a Cloudflare Tunnel for public HTTPS.

```text
Recruiter → HTTPS (Cloudflare) → Tunnel → VM → Docker app :7860 → ./data
```

Do **not** open ingress port `7860` on the Oracle security list when using a tunnel. SSH (22) is enough for admin access.

Related files:

- [`docker-compose.yml`](../docker-compose.yml) — base service
- [`docker-compose.prod.yml`](../docker-compose.prod.yml) — public VM (`PUBLIC_CHAT_ONLY`, no backend bind-mount)
- [`docker-compose.override.yml`](../docker-compose.override.yml) — local only (auto-loaded)
- [`scripts/oracle-bootstrap.sh`](../scripts/oracle-bootstrap.sh) — Docker install + prod `up --build`

---

## 0. Prerequisites (laptop)

1. Push the branch that contains the Oracle deploy files (e.g. `deploy/oracle`), or merge to `main` first:

   ```bash
   git push -u origin deploy/oracle
   ```

2. Have ready:

   - An SSH key pair (`~/.ssh/id_ed25519.pub` or similar)
   - An LLM API key ([NVIDIA NIM](https://build.nvidia.com/) or [Groq](https://console.groq.com/))
   - A strong `OWNER_SECRET` (if it contains `$`, you will write `$$` in `.env` on the VM)

3. Optional but better for a stable recruiter URL: a domain on Cloudflare.

---

## 1. Create the Oracle Always Free VM

1. Sign up / sign in at [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
2. Open **Compute → Instances → Create instance**.
3. Suggested settings:

   - **Name:** e.g. `profile-rag-agent`
   - **Image:** Canonical Ubuntu 22.04 or 24.04
   - **Shape:** Always Free eligible — prefer **VM.Standard.A1.Flex** (Ampere ARM) if capacity allows; otherwise an Always Free x86 shape
   - **Networking:** VCN with a **public IP**
   - **SSH keys:** paste your **public** key

4. Create the instance; wait until state is **Running**.
5. Copy the **Public IP**.

**Networking:** keep SSH (22) open (ideally restricted to your IP). Outbound internet must work for Docker pulls and LLM API calls. Do not open `7860` if using Cloudflare Tunnel.

---

## 2. SSH into the VM

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<VM_PUBLIC_IP>
```

On Oracle Ubuntu images the default user is usually `ubuntu`. Accept the host key on first connect.

---

## 3. Clone the repo

```bash
sudo apt-get update
sudo apt-get install -y git curl

git clone -b deploy/oracle https://github.com/<YOUR_USERNAME>/profile-rag-agent.git
cd profile-rag-agent
```

Use `-b main` after merging. For a private repo, use SSH clone + a deploy key, or HTTPS with a personal access token.

---

## 4. First bootstrap (Docker + `.env`)

```bash
bash scripts/oracle-bootstrap.sh
```

On first run this:

- Installs Docker Engine + Compose plugin if missing
- Creates `data/`
- Copies `.env.example` → `.env`
- Exits and asks you to edit `.env`

If Docker was just installed and you hit permission errors:

```bash
newgrp docker
# or log out and SSH back in
```

---

## 5. Configure `.env` on the VM

```bash
nano .env
```

Minimum:

```env
LLM_PROVIDER=NVIDIA
LLM_API_KEY=nvapi-...your-key...
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=meta/llama-3.1-8b-instruct

PUBLIC_CHAT_ONLY=true
OWNER_SECRET=your-long-secret
```

**`OWNER_SECRET` and Compose:**

- In `.env`, each `$` must be written as `$$` (Compose interpolation)
- Example: real secret `abc$xyz` → file value `OWNER_SECRET=abc$$xyz`
- When unlocking the UI, type the **literal** secret (`abc$xyz`, one `$`)

Optional: `GITHUB_TOKEN` for higher GitHub API rate limits.

---

## 6. Build and start the app

```bash
bash scripts/oracle-bootstrap.sh
```

Or:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

First build can take several minutes.

Verify on the VM:

```bash
curl -s http://127.0.0.1:7860/api/health
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=80
```

Expect JSON with `"status":"ok"`. The app is not public yet — only on localhost (and via SSH).

---

## 7. Cloudflare Tunnel (public HTTPS)

### 7a. Account

1. Sign in at [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) (or the Cloudflare dashboard).
2. Prefer a **named tunnel** (survives reboots) over a one-off quick tunnel.

### 7b. Create a named tunnel

1. Zero Trust → **Networks → Tunnels → Create a tunnel**
2. Choose **Cloudflared**
3. Name it e.g. `profile-rag-oracle`
4. Copy the install token / command Cloudflare shows

### 7c. Install `cloudflared` on the VM

Check architecture:

```bash
uname -m
# aarch64 → arm64 package
# x86_64  → amd64 package
```

Install from Cloudflare’s [installation docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/), for example:

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
# x86_64: use cloudflared-linux-amd64.deb instead

sudo dpkg -i cloudflared.deb
cloudflared --version
```

### 7d. Run the tunnel as a service

Use the token from Cloudflare. **Never commit the token.**

```bash
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

### 7e. Public hostname → app

In the tunnel **Public Hostname** settings:

| Field | Value |
|--------|--------|
| Subdomain | e.g. `chat` or `profile` |
| Domain | your Cloudflare domain |
| Type | HTTP |
| URL | `localhost:7860` |

Save and wait a minute for DNS. For a quick test without a domain, Cloudflare’s trycloudflare / quick tunnel flow works, but a named tunnel + your domain is better for recruiters.

---

## 8. Create the agent and share the link

1. Open `https://<your-hostname>/`
2. Unlock the builder with `OWNER_SECRET` (literal `$`, not `$$`)
3. Fill profile / resume / FAQ / GitHub
4. Create agent
5. Share `https://<your-hostname>/a/<agent_id>`

Recruiter check: open the chat URL in a private window (no owner secret). Ask an FAQ question (e.g. relocate). Off-profile questions should refuse.

---

## 9. Ongoing operations

**Update after code changes:**

```bash
cd ~/profile-rag-agent   # or your clone path
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

**Logs:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
```

**Restart:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart
```

After PDF / chunk / GitHub pipeline changes, recreate the agent or call `POST /api/agents/{id}/reindex` with the owner header.

---

## 10. Troubleshooting

| Problem | Fix |
|--------|-----|
| `Invalid or missing owner secret` | Escape `$` as `$$` in `.env`; recreate containers; unlock with the literal secret |
| Docker permission denied | `newgrp docker` or re-login after bootstrap |
| Health check fails | Check logs; confirm `LLM_*` in `.env`; wait for first embedding download |
| Tunnel up, site down | Confirm `curl http://127.0.0.1:7860/api/health`; hostname → `http://localhost:7860`; `systemctl status cloudflared` |
| Out of Always Free capacity | Try another region / Ampere shape, or retry later |
| Wrong `cloudflared` arch | Match `.deb` to `uname -m` (`arm64` vs `amd64`) |

---

## Checklist

- [ ] VM running, SSH works
- [ ] Repo cloned (correct branch)
- [ ] `.env` set (`LLM_API_KEY`, `OWNER_SECRET`, `PUBLIC_CHAT_ONLY=true`)
- [ ] `curl http://127.0.0.1:7860/api/health` OK
- [ ] Cloudflare Tunnel service running
- [ ] HTTPS hostname opens the builder
- [ ] Agent created; `/a/<id>` works in a private window
