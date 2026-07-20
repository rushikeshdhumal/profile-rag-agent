from __future__ import annotations

import secrets
from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_owner(x_owner_secret: str | None = Header(default=None, alias="X-Owner-Secret")) -> None:
    settings = get_settings()
    expected = settings.owner_secret.strip()
    if not expected:
        # Local/dev: allow mutations when no secret is configured
        if settings.public_chat_only:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OWNER_SECRET must be set when PUBLIC_CHAT_ONLY is enabled",
            )
        return
    provided = (x_owner_secret or "").strip()
    # compare_digest raises on unequal length; treat that as a failed auth check
    ok = False
    if provided and len(provided) == len(expected):
        ok = secrets.compare_digest(provided, expected)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing owner secret",
        )


def owner_auth_required() -> bool:
    settings = get_settings()
    return bool(settings.owner_secret.strip()) or settings.public_chat_only
