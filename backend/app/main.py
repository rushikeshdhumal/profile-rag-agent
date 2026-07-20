from __future__ import annotations

import logging
import os
from pathlib import Path

# Reduce noisy Chroma telemetry failures on some platforms
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_DISABLED", "1")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import owner_auth_required
from app.config import get_settings
from app.llm import llm_configured
from app.routes import agents, chat
from app.schemas import HealthResponse

logging.basicConfig(level=logging.INFO)
# Chroma/PostHog SDK mismatch can still emit ERROR logs; silence that logger
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="Profile RAG Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agents.router)
app.include_router(chat.router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_configured=llm_configured(),
        public_chat_only=settings.public_chat_only,
        owner_auth_required=owner_auth_required(),
    )


@app.get("/api/config/public")
def public_config() -> dict:
    return {
        "public_chat_only": settings.public_chat_only,
        "owner_auth_required": owner_auth_required(),
    }


def _static_dir() -> Path | None:
    if settings.static_dir and Path(settings.static_dir).exists():
        return Path(settings.static_dir)
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
        Path("/app/frontend/dist"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


static = _static_dir()
if static:
    assets = static / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(static / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = static / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static / "index.html")
else:
    logger.warning("Frontend dist not found; API-only mode")
