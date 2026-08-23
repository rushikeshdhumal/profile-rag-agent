#!/usr/bin/env bash
# Bootstrap Profile RAG Agent on an Ubuntu Oracle Always Free VM.
# Run from the repo root after cloning. Does not configure Cloudflare Tunnel
# (that needs a Cloudflare account token — see README).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Profile RAG Agent — Oracle bootstrap"

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker Engine + Compose plugin"
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER" || true
  echo "Docker installed. If 'docker' fails with permission denied, log out/in (or run: newgrp docker)."
fi

mkdir -p data

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
  echo "    Edit .env now: set LLM_API_KEY, OWNER_SECRET (escape \$ as \$\$), PUBLIC_CHAT_ONLY=true"
  echo "    Then re-run: bash scripts/oracle-bootstrap.sh"
  exit 0
fi

if grep -Eq '^LLM_API_KEY=[[:space:]]*$' .env 2>/dev/null; then
  echo "WARNING: LLM_API_KEY looks empty in .env — set it before expecting chat to work."
fi

echo "==> Building and starting (production compose)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "==> Waiting for health"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:7860/api/health >/dev/null; then
    echo "Healthy: http://127.0.0.1:7860/api/health"
    echo
    echo "Next: expose HTTPS with Cloudflare Tunnel (see README — Deploy on Oracle Always Free)."
    echo "Do not open ingress port 7860 on the Oracle security list when using a tunnel."
    exit 0
  fi
  sleep 2
done

echo "Health check did not succeed yet. Check: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=80"
exit 1
