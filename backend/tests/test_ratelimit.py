from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.ratelimit import _agent_daily, _buckets, enforce_chat_rate_limit


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, host: str = "1.2.3.4"):
        self.headers = headers or {}
        self.client = _FakeClient(host)


@pytest.fixture(autouse=True)
def _reset_ratelimit_state():
    _buckets.clear()
    _agent_daily.clear()
    yield
    _buckets.clear()
    _agent_daily.clear()


def test_enforce_chat_rate_limit_allows_burst_then_blocks(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "60")
    monkeypatch.setenv("RATE_LIMIT_BURST", "3")
    monkeypatch.setenv("AGENT_DAILY_CHAT_LIMIT", "1000")
    from app.config import get_settings

    get_settings.cache_clear()

    request = _FakeRequest()
    for _ in range(3):
        enforce_chat_rate_limit(request, "agent-1")  # should not raise

    with pytest.raises(HTTPException) as exc_info:
        enforce_chat_rate_limit(request, "agent-1")
    assert exc_info.value.status_code == 429


def test_enforce_chat_rate_limit_disabled_never_blocks(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    request = _FakeRequest()
    for _ in range(50):
        enforce_chat_rate_limit(request, "agent-1")  # should never raise


def test_enforce_chat_rate_limit_prefers_cf_connecting_ip(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "60")
    monkeypatch.setenv("RATE_LIMIT_BURST", "1")
    monkeypatch.setenv("AGENT_DAILY_CHAT_LIMIT", "1000")
    from app.config import get_settings

    get_settings.cache_clear()

    request_a = _FakeRequest(headers={"CF-Connecting-IP": "9.9.9.9"}, host="1.1.1.1")
    request_b = _FakeRequest(headers={"CF-Connecting-IP": "8.8.8.8"}, host="1.1.1.1")

    enforce_chat_rate_limit(request_a, "agent-1")
    enforce_chat_rate_limit(request_b, "agent-1")  # different CF IP, same bucket-host: should not raise


def test_enforce_chat_rate_limit_enforces_agent_daily_cap(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "6000")
    monkeypatch.setenv("RATE_LIMIT_BURST", "6000")
    monkeypatch.setenv("AGENT_DAILY_CHAT_LIMIT", "2")
    from app.config import get_settings

    get_settings.cache_clear()

    request = _FakeRequest()
    enforce_chat_rate_limit(request, "agent-daily")
    enforce_chat_rate_limit(request, "agent-daily")
    with pytest.raises(HTTPException) as exc_info:
        enforce_chat_rate_limit(request, "agent-daily")
    assert exc_info.value.status_code == 429
