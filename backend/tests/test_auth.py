from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import owner_auth_required, require_owner


def test_require_owner_allows_when_no_secret_configured(monkeypatch):
    monkeypatch.setenv("OWNER_SECRET", "")
    monkeypatch.setenv("PUBLIC_CHAT_ONLY", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    require_owner(x_owner_secret=None)  # should not raise


def test_require_owner_rejects_when_public_chat_only_and_no_secret(monkeypatch):
    monkeypatch.setenv("OWNER_SECRET", "")
    monkeypatch.setenv("PUBLIC_CHAT_ONLY", "true")
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc_info:
        require_owner(x_owner_secret=None)
    assert exc_info.value.status_code == 503


def test_require_owner_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("OWNER_SECRET", "correct-horse-battery-staple")
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc_info:
        require_owner(x_owner_secret="wrong")
    assert exc_info.value.status_code == 401


def test_require_owner_accepts_correct_secret(monkeypatch):
    monkeypatch.setenv("OWNER_SECRET", "correct-horse-battery-staple")
    from app.config import get_settings

    get_settings.cache_clear()

    require_owner(x_owner_secret="correct-horse-battery-staple")  # should not raise


def test_require_owner_handles_mismatched_length_without_crashing(monkeypatch):
    # secrets.compare_digest raises on unequal-length inputs; the app must
    # treat that as a failed auth check, not a 500.
    monkeypatch.setenv("OWNER_SECRET", "a-very-long-owner-secret-value")
    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exc_info:
        require_owner(x_owner_secret="short")
    assert exc_info.value.status_code == 401


def test_owner_auth_required_reflects_settings(monkeypatch):
    monkeypatch.setenv("OWNER_SECRET", "")
    monkeypatch.setenv("PUBLIC_CHAT_ONLY", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    assert owner_auth_required() is False

    monkeypatch.setenv("PUBLIC_CHAT_ONLY", "true")
    get_settings.cache_clear()
    assert owner_auth_required() is True
