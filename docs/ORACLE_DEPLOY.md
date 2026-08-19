# Oracle Always Free deployment guide

End-to-end steps to run Profile RAG Agent on an Oracle Cloud Always Free VM with a Cloudflare Tunnel for public HTTPS.

```text
Recruiter → HTTPS (Cloudflare) → Tunnel → VM → Docker app :7860 → ./data
```

Do **not** open ingress port `7860` on the Oracle security list when using a tunnel. SSH (22) is enough for admin access.

Working public example from this repo's author: [https://chat.rdhumal.com/a/5d0805be2236](https://chat.rdhumal.com/a/5d0805be2236) (`chat.` subdomain → Cloudflare Tunnel → `localhost:7860`).

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

3. A domain you control, added to Cloudflare, for a stable recruiter URL (buy or connect; `*.github.io` cannot be a tunnel hostname). A `chat.` subdomain is enough; the apex can host a portfolio later.

---

## Glossary (Oracle Cloud terms used below)

| Term | Plain-English meaning |
|------|------------------------|
| **VCN** (Virtual Cloud Network) | Your own private network inside Oracle Cloud — like a virtual data center. Everything else (subnets, VMs, gateways) lives inside a VCN. |
| **CIDR block** | A notation for an IP address range, e.g. `10.0.0.0/16` means "all addresses from `10.0.0.0` to `10.0.255.255"`. The `/16` is the size of the range. |
| **Subnet** | A smaller slice of the VCN's IP range where you actually place VMs, e.g. `10.0.0.0/24` inside a `10.0.0.0/16` VCN. |
| **Regional vs Availability Domain (AD)-specific subnet** | A *regional* subnet spans all ADs in the region, so a VM in any AD can use it. An *AD-specific* subnet is tied to one AD only. Regional is simpler and is the current default. |
| **Availability Domain (AD)** | A physically separate data center within an Oracle region. A region typically has 3 ADs (AD-1, AD-2, AD-3) for redundancy. |
| **Fault Domain** | A further subdivision *within* an AD, isolating hardware failures. You generally don't need to pick one manually. |
| **Internet Gateway (IGW)** | The component that lets a VCN/subnet reach and be reached from the public internet. A "public" subnet routes traffic through one. |
| **NAT Gateway** | Lets a *private* subnet reach the internet *outbound only* (no inbound), without giving VMs public IPs. Not needed here since we use a public subnet. |
| **Route table** | The set of rules that decide where network traffic goes (e.g. "send anything not on my private network to the Internet Gateway"). |
| **Security list / NSG (Network Security Group)** | Cloud-level firewall rules (allowed inbound/outbound ports and source IPs), separate from the OS firewall. |
| **DNS hostnames / DNS label** | Lets Oracle auto-generate internal DNS names for your instances (e.g. `myvm.profilerag.oraclevcn.com`). Not related to your public Cloudflare domain. |
| **Boot volume** | The virtual disk that holds the VM's operating system, similar to a laptop's internal SSD. |
| **Shape** | Oracle's term for a VM "size" (CPU architecture + CPU count + RAM), e.g. `VM.Standard.A1.Flex` (ARM, flexible CPU/RAM) or `VM.Standard.E2.1.Micro` (small x86). |
| **OCPU** | Oracle's unit of CPU allocation, roughly one full physical CPU core (with hyper-threading counted as 2 vCPUs on some shapes). |
| **Confidential computing** | Encrypts VM memory so even the cloud provider can't read it while running. Useful for highly regulated workloads — not needed for a personal RAG chatbot. |
| **Compartment** | An Oracle Cloud folder-like construct for organizing and permissioning resources. The default compartment is fine for a single personal project. |

---

## 1. Create the network (VCN + subnet)

If you already have a VCN with a public subnet, skip to [Section 2](#2-create-the-oracle-always-free-vm). Otherwise, create both first — Compute instances need a subnet to attach to.

### 1a. Create the VCN

**Networking → Virtual Cloud Networks → Create VCN.**

| Setting | Value | Why |
|--------|-------|-----|
| Name | `profile-rag-vcn` | Just a label |
| IPv4 CIDR Blocks | `10.0.0.0/16` | Standard private range; plenty of address space for one VM |
| Use DNS hostnames in this VCN | **On** | Lets instances get auto-generated internal DNS names (harmless, sometimes required by other services) |
| DNS Label | leave auto-suggested (e.g. `profilerag`) | Required once DNS hostnames is on; only affects internal `*.oraclevcn.com` names, not your public URL |
| DNS Domain Name | leave auto | Don't customize |
| IPv6 Prefixes / Assign Oracle allocated IPv6 /56 | **Off** | Not needed; this deploy is IPv4-only |
| BYOIPv6 Prefix / ULA Prefixes | leave empty | Not needed |
| Tags / Security Attributes | leave empty | Optional metadata, not needed for a personal project |

Click **Create VCN**.

### 1b. Create a public subnet

Inside the new VCN: **Subnets → Create Subnet.**

| Setting | Value | Why |
|--------|-------|-----|
| Name | `public-subnet` | Clear label |
| Subnet Type | **Regional** | Simpler; any AD can use it (current Oracle default) |
| IPv4 CIDR Block | `10.0.0.0/24` | A slice of the VCN's `10.0.0.0/16`; enough for one VM |
| IPv6 Prefixes | leave at `0` | Not needed |
| Route Table | **Default Route Table for &lt;vcn&gt;** | Must route `0.0.0.0/0` to an Internet Gateway for public access (see below) |
| Subnet Access | **Public Subnet** | Gives the VM a public IP for SSH and lets it reach the internet for Docker pulls / LLM API calls |
| Use DNS hostnames in this Subnet | **On** | Matches the VCN setting |
| DNS Label | leave auto | Only affects internal DNS names |
| DNS Domain Name | leave auto | Don't customize |
| DHCP Options | **Default DHCP Options** | Standard IP assignment settings; no changes needed |
| Security Lists | **Default Security List for &lt;vcn&gt;** | You'll add an SSH rule here (or confirm it's already present) |
| Resource logging | **Off** | Extra logging/cost not needed for a personal project |

Click **Create Subnet**.

### 1c. Add an Internet Gateway and a public route table

If Oracle's "Create VCN" wizard offered a one-click "VCN with Internet Connectivity" option, this is already done. If you created the VCN by hand, do this **before** you expect SSH from the internet.

1. **Networking → Virtual Cloud Networks → &lt;your VCN&gt; → Internet Gateways → Create Internet Gateway.** Name it `igw`, leave it **Enabled**.

2. Add a default route. Prefer a **new** route table if the default one rejects an IGW target (see below):

   **Route Tables → Create Route Table** (e.g. `public-rt`), then add:

   | Field | Value |
   |--------|--------|
   | Destination CIDR | `0.0.0.0/0` |
   | Target type | **Internet Gateway** (not Private IP) |
   | Target | `igw` |

3. **Subnets → public-subnet → Edit** → set **Route Table** to `public-rt`.

If editing the **default** route table fails with:

> Rules in the route table must use private IP as a target. Or the route table can be empty (no rules).

that table is treated as private-only. Do not force an IGW onto it. Create `public-rt` as above and attach it to the **public** subnet. A public IP on the instance is not enough without this route — SSH will **time out**.

### 1d. Confirm the security list allows SSH

**Security Lists → Default Security List → Ingress Rules** should include (or you should add):

| Source CIDR | IP Protocol | Destination Port Range |
|-------------|-------------|--------------------------|
| `0.0.0.0/0` (or your IP `/32` for tighter security) | TCP | `22` |

**Do not** add a rule for port `7860` — the app stays reachable only via the Cloudflare Tunnel, not directly from the internet.

---

## 2. Create the Oracle Always Free VM

1. Sign up / sign in at [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
2. Open **Compute → Instances → Create instance**.
3. Suggested settings:

   - **Name:** e.g. `profile-rag-agent`
   - **Image:** Canonical Ubuntu 22.04 or 24.04
   - **Shape:** Always Free eligible — prefer **VM.Standard.A1.Flex** (Ampere ARM) if capacity allows; otherwise an Always Free x86 shape such as **VM.Standard.E2.1.Micro** (see [capacity errors](#capacity-errors-out-of-capacity-for-shape) below)
   - **Confidential computing:** leave **off** — it encrypts VM memory for high-sensitivity workloads and is not needed for this app; it can also block certain image/shape combinations
   - **Networking:** select the VCN and public subnet created in [Section 1](#1-create-the-network-vcn--subnet); ensure **Assign a public IPv4 address** is on
   - **SSH keys:** upload your **public** key file (the `.pub` file, never the private key)
   - **Boot volume:** leave **"Specify a custom boot volume size and performance"** off (the ~47 GB default is enough); leave **"Use in-transit encryption"** on if offered; leave **"Encrypt this volume with a key that you manage"** off (Oracle-managed encryption is fine — a customer-managed key needs a Vault you don't need for this project)

4. Create the instance; wait until state is **Running**.
5. Copy the **Public IP**.

**Networking:** keep SSH (22) open (ideally restricted to your IP). Outbound internet must work for Docker pulls and LLM API calls. Do not open `7860` if using Cloudflare Tunnel.

### Capacity errors ("Out of capacity for shape ...")

Oracle Always Free Ampere (`VM.Standard.A1.Flex`) capacity is shared across all free-tier users per region and availability domain, and often runs out. If you see:

> Out of capacity for shape VM.Standard.A1.Flex in availability domain AD-x.

this is a temporary regional shortage, not a mistake in your config. Options, roughly in order of effort:

1. **Retry later**, cycling through AD-1 / AD-2 / AD-3, without specifying a fault domain.
2. **Request a smaller A1 shape** — e.g. 1 OCPU / 6 GB RAM instead of a larger flexible size; smaller requests are sometimes easier to place.
3. **Switch to an Always Free x86 shape** instead of Ampere, e.g. **VM.Standard.E2.1.Micro**. Everything in this guide still works — just use the `amd64` `cloudflared` package instead of `arm64` in [Section 8c](#8c-install-cloudflared-on-the-vm) (check with `uname -m`).
4. Avoid extra constraints that reduce placement options (e.g. confidential computing, custom boot volume shapes) until the instance is created.

---

## 3. SSH into the VM

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<VM_PUBLIC_IP>
```

On Oracle Ubuntu images the default user is usually `ubuntu`. Accept the host key on first connect.

If you get `ssh: connect to host <IP> port 22: Connection timed out`, packets are not reaching the VM. That is almost always missing IGW / public route table (Section 1c) or missing security-list TCP 22 (Section 1d) — not a bad SSH key (`Permission denied` would mean the key). Confirm the instance is **Running**, then:

```powershell
Test-NetConnection <VM_PUBLIC_IP> -Port 22
```

---

## 4. Clone the repo

```bash
sudo apt-get update
sudo apt-get install -y git curl

git clone https://github.com/<YOUR_USERNAME>/profile-rag-agent.git
# If deploy files are only on a feature branch:  git clone -b deploy/oracle ...
cd profile-rag-agent
```

For a private repo, use SSH clone + a deploy key, or HTTPS with a personal access token.

---

## 5. First bootstrap (Docker + `.env`)

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

#### Ampere Ubuntu apt mirror DNS

Oracle ARM images often list `http://iad-ad-1.clouds.ports.ubuntu.com/ubuntu-ports` (the AD number varies). That hostname frequently **does not resolve**, so `apt-get` fails while `ports.ubuntu.com` and `download.docker.com` still work. Typical symptom: Docker `.deb` files download, then `pigz` fails with `Could not resolve 'iad-ad-*.clouds.ports.ubuntu.com'`.

```bash
sudo sed -i 's|http://[^/]*clouds.ports.ubuntu.com/ubuntu-ports|http://ports.ubuntu.com/ubuntu-ports|g' /etc/apt/sources.list
sudo grep -R "clouds.ports.ubuntu.com" /etc/apt/sources.list /etc/apt/sources.list.d/ || true
sudo apt-get update
```

Then re-run the bootstrap script (or install Docker packages by hand). Also replace the same host in any file under `/etc/apt/sources.list.d/` if `sed` did not catch it.

---

## 6. Configure `.env` on the VM

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

## 7. Build and start the app

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

## 8. Cloudflare Tunnel (public HTTPS)

A tunnel is recommended, not mandatory. Opening TCP **7860** on the security list gives `http://<public-ip>:7860` for a test (no HTTPS). Recruiters should get `https://chat.<your-domain>/a/<id>`.

You need a **domain you control** in Cloudflare (buy or connect). You cannot use `you.github.io`. One domain can later serve a portfolio on `@` / `www` and the agent on `chat.` — do not point the same hostname at both GitHub Pages and the tunnel.

### 8a. Account and domain

1. Sign in at [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) (or the Cloudflare dashboard).
2. **Buy** a domain or **Connect** one you already own. Skip **Transfer** unless you are moving a registration you already have.
3. Prefer a **named tunnel** (survives reboots) over a one-off `trycloudflare.com` URL.

### 8b. Create a named tunnel

1. Zero Trust → **Networks → Tunnels → Create a tunnel**
2. Choose **Cloudflared**
3. Name it e.g. `profile-rag-oracle`
4. Installer OS: **Debian** (Ubuntu is Debian-based). Architecture: **arm64** on Ampere (`uname -m` → `aarch64`); **amd64** on x86 (`x86_64`).
5. Copy the install token / command. **Never commit the token.**

During `apt`/`dpkg` you may see **needrestart** prompts (newer kernel, “which services to restart”). Finish the install; reboot later if you want the new kernel. `cloudflared` as a systemd service and Compose `restart: unless-stopped` come back after reboot.

### 8c. Install `cloudflared` on the VM

```bash
uname -m
# aarch64 → arm64 package
# x86_64  → amd64 package
```

Follow Cloudflare’s [installation docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) or the dashboard command, for example:

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
# x86_64: use cloudflared-linux-amd64.deb instead

sudo dpkg -i cloudflared.deb
cloudflared --version
```

### 8d. Run the tunnel as a service

```bash
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

`Active: active (running)` and **Healthy** in the dashboard are enough. **Routes: 0** means the tunnel is up but nothing is published yet.

### 8e. Published application route (public hostname)

The current Zero Trust UI uses **Routes**, not a separate “Public hostname” tab.

1. Open the tunnel → **Add route** (not a private CIDR / WARP route).
2. Type: **Published application**.
3. Fill in:

| Field | Value |
|--------|--------|
| Hostname | e.g. `chat.example.com` |
| Type / service | **HTTP** |
| URL | `http://localhost:7860` |

Do **not** set the origin to the Oracle public IP. Cloudflare should create a CNAME from `chat.example.com` to `*.cfargotunnel.com`.

4. Wait 1–2 minutes. Open `https://chat.example.com/`.

Without a domain, a quick tunnel (`cloudflared tunnel --url http://localhost:7860`) yields a temporary `*.trycloudflare.com` URL that can change on restart — fine for a test, poor on a resume.

---

## 9. Create the agent and share the link

1. Open `https://<your-hostname>/` (e.g. `https://chat.example.com/`)
2. Unlock the builder with `OWNER_SECRET` (literal `$`, not `$$`)
3. Fill profile / resume / FAQ / GitHub
4. Create agent
5. Share **only** `https://<your-hostname>/a/<agent_id>` with recruiters — not `OWNER_SECRET`, and not the builder root if you want them to land in chat

Recruiter check: open the chat URL in a **private / incognito** window (no owner secret stored). Ask an FAQ question (e.g. relocate). Off-profile questions should refuse. The builder at `/` stays locked when `PUBLIC_CHAT_ONLY=true`.

---

## 10. Ongoing operations

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

## 11. Troubleshooting

| Problem | Fix |
|--------|-----|
| `ssh: connect to host … port 22: Connection timed out` | IGW + **public** route table (`0.0.0.0/0` → Internet Gateway) + security-list TCP 22. See Sections 1c–1d. |
| Route table: *must use private IP as a target* | Default RT is private-only. Create `public-rt` with IGW and attach it to the public subnet. Target type must be **Internet Gateway**. |
| `Could not resolve iad-ad-*.clouds.ports.ubuntu.com` | Point apt at `http://ports.ubuntu.com/ubuntu-ports` (Section 5). |
| `Invalid or missing owner secret` | Escape `$` as `$$` in `.env`; recreate containers; unlock with the literal secret |
| Docker permission denied | `newgrp docker` or re-login after bootstrap |
| Health check fails | Check logs; confirm `LLM_*` in `.env`; wait for first embedding download |
| Tunnel Healthy, Routes 0 | Add a **Published application** route to `http://localhost:7860` |
| Tunnel up, site 502 / down | Confirm `curl http://127.0.0.1:7860/api/health`; origin must be localhost, not the VM public IP; `systemctl status cloudflared` |
| `Out of capacity for shape ...` when creating the instance | Regional Always Free capacity shortage, not a config error — see [Capacity errors](#capacity-errors-out-of-capacity-for-shape) in Section 2 |
| Wrong `cloudflared` arch | Ubuntu Ampere: Debian **arm64**. Match `.deb` to `uname -m` |
| Confidential computing blocked for Ubuntu + A1 | Leave it **off** — not needed for this app |

---

## Checklist

- [ ] VCN + public subnet + Internet Gateway + public route table (`0.0.0.0/0` → IGW)
- [ ] Security list allows SSH (22); port 7860 stays closed when using a tunnel
- [ ] VM running, SSH works
- [ ] Repo cloned (correct branch)
- [ ] `.env` set (`LLM_API_KEY`, `OWNER_SECRET`, `PUBLIC_CHAT_ONLY=true`)
- [ ] `curl http://127.0.0.1:7860/api/health` OK
- [ ] Cloudflare Tunnel service running (Healthy)
- [ ] Published application route: `chat.<domain>` → `http://localhost:7860`
- [ ] HTTPS hostname opens the builder; unlock with literal `OWNER_SECRET`
- [ ] Agent created; `/a/<id>` works in a private window without the owner secret
