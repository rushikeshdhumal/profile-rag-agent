from __future__ import annotations

import logging
import os
from pathlib import Path

# Reduce noisy Chroma telemetry failures on some platforms
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_DISABLED", "1")

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.auth import owner_auth_required, require_owner
from app.config import get_settings
from app.llm import llm_configured
from app.observability import configure_logging, render_prometheus_text, request_context_middleware
from app.routes import agents, chat
from app.schemas import HealthResponse

settings = get_settings()
configure_logging(json_logs=settings.json_logs)
logger = logging.getLogger(__name__)

app = FastAPI(title="Profile RAG Agent", version="0.1.0")
app.middleware("http")(request_context_middleware)

_cors_origins = settings.cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
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


@app.get("/api/health/ready")
def readiness() -> dict:
    checks: dict[str, str] = {}

    try:
        from app.embeddings import get_embedding_model

        get_embedding_model()
        checks["embeddings"] = "ok"
    except Exception as exc:  # pragma: no cover - depends on model download
        checks["embeddings"] = f"error: {exc}"

    try:
        probe = get_settings().data_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["data_dir"] = "ok"
    except Exception as exc:
        checks["data_dir"] = f"error: {exc}"

    if any(v != "ok" for v in checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}


@app.get("/api/metrics", dependencies=[Depends(require_owner)])
def metrics() -> PlainTextResponse:
    return PlainTextResponse(render_prometheus_text())


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


def resolve_static_path(static: Path, full_path: str) -> Path | None:
    """Resolve a requested SPA path under `static`, refusing to escape it.

    Without this, `full_path` from a path-type route parameter can contain
    `../` segments; FileResponse would happily serve files outside `dist`.
    """
    candidate = (static / full_path).resolve()
    static_resolved = static.resolve()
    if candidate != static_resolved and static_resolved not in candidate.parents:
        return None
    return candidate


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
        candidate = resolve_static_path(static, full_path)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Not Found")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static / "index.html")
else:
    logger.warning("Frontend dist not found; API-only mode")
