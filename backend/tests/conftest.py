from __future__ import annotations

import gc
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own DATA_DIR and a cleared settings cache, since
    app.config.get_settings is process-wide lru_cache'd."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OWNER_SECRET", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("PUBLIC_CHAT_ONLY", "false")
    monkeypatch.setenv("EMBEDDING_THREADS", "1")

    from app.config import get_settings
    from app.ratelimit import _agent_daily, _buckets

    get_settings.cache_clear()
    _buckets.clear()
    _agent_daily.clear()

    yield

    from app.bm25 import invalidate_all_bm25_indexes
    from app.vectorstore import close_all_clients

    close_all_clients()
    invalidate_all_bm25_indexes()
    get_settings.cache_clear()
    _buckets.clear()
    _agent_daily.clear()
    gc.collect()


@pytest.fixture
def fake_llm(monkeypatch):
    """Stub chat_completion so tests never call a real LLM provider."""

    def _fake(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        return "This is a stubbed answer based on the provided context."

    monkeypatch.setattr("app.llm.chat_completion", _fake)
    monkeypatch.setattr("app.rag.chat_completion", _fake)
    return _fake


@pytest.fixture
def client(fake_llm):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
