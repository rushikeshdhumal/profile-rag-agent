from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill_monotonic)
_agent_daily: dict[tuple[str, str], int] = {}  # (agent_id, date) -> count
_PRUNE_THRESHOLD = 10_000


def _client_key(request: Request) -> str:
    # Traffic arrives via Cloudflare Tunnel; CF-Connecting-IP is the real client IP.
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _take_token(key: str, rate_per_min: float, burst: float) -> bool:
    now = time.monotonic()
    with _lock:
        tokens, last = _buckets.get(key, (burst, now))
        elapsed = max(0.0, now - last)
        tokens = min(burst, tokens + elapsed * (rate_per_min / 60.0))
        if tokens < 1.0:
            _buckets[key] = (tokens, now)
            return False
        tokens -= 1.0
        _buckets[key] = (tokens, now)
        return True


def _bump_agent_daily(agent_id: str, daily_limit: int) -> bool:
    today = datetime.now(UTC).date().isoformat()
    key = (agent_id, today)
    with _lock:
        if len(_agent_daily) > _PRUNE_THRESHOLD:
            for stale_key in [k for k in _agent_daily if k[1] != today]:
                del _agent_daily[stale_key]
        count = _agent_daily.get(key, 0)
        if count >= daily_limit:
            return False
        _agent_daily[key] = count + 1
        return True


def enforce_chat_rate_limit(request: Request, agent_id: str) -> None:
    """In-process token bucket per client + a per-agent daily cap.

    No Redis: a single-process deploy (Oracle Always Free VM) doesn't need a
    shared store, and this keeps the free tier's LLM budget from being drained
    by a scripted client hitting the public chat endpoint.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    client_key = _client_key(request)
    if not _take_token(client_key, settings.rate_limit_per_minute, settings.rate_limit_burst):
        logger.warning("Rate limit exceeded for client %s", client_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again shortly.",
        )

    if not _bump_agent_daily(agent_id, settings.agent_daily_chat_limit):
        logger.warning("Daily chat limit exceeded for agent %s", agent_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This agent has reached its daily chat limit. Please try again tomorrow.",
        )
