from __future__ import annotations


def _create_agent(client, display_name: str = "Test Candidate") -> dict:
    resp = client.post(
        "/api/agents",
        data={
            "display_name": display_name,
            "headline": "Backend engineer",
            "linkedin_text": "About: I build reliable backend systems.",
            "faq": '{"open_to_relocate": "Yes, anywhere in the US", "notice_period": "2 weeks"}',
        },
        files={
            "resume": (
                "resume.md",
                b"# Resume\n\n## Experience\n\nSenior Engineer at Acme Corp, building backend "
                b"systems and APIs for internal tooling used across the company.",
                "text/markdown",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_readiness_endpoint(client):
    resp = client.get("/api/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_create_agent_and_fetch(client):
    meta = _create_agent(client)
    assert meta["display_name"] == "Test Candidate"
    assert meta["chunk_count"] > 0

    resp = client.get(f"/api/agents/{meta['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == meta["id"]


def test_get_unknown_agent_returns_404(client):
    resp = client.get("/api/agents/does-not-exist")
    assert resp.status_code == 404


def test_create_agent_requires_display_name(client):
    resp = client.post("/api/agents", data={"display_name": ""})
    assert resp.status_code == 400


def test_chat_returns_grounded_answer(client, fake_llm):
    meta = _create_agent(client)
    resp = client.post(
        "/api/chat",
        json={"agent_id": meta["id"], "message": "What is your notice period?", "history": []},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"]
    assert isinstance(body["sources"], list)


def test_chat_unknown_agent_returns_404(client):
    resp = client.post(
        "/api/chat",
        json={"agent_id": "does-not-exist", "message": "hello", "history": []},
    )
    assert resp.status_code == 404


def test_chat_rejects_oversized_history(client):
    meta = _create_agent(client)
    history = [{"role": "user", "content": "hi"} for _ in range(41)]
    resp = client.post(
        "/api/chat",
        json={"agent_id": meta["id"], "message": "hello", "history": history},
    )
    assert resp.status_code == 422


def test_reindex_agent(client):
    meta = _create_agent(client)
    resp = client.post(f"/api/agents/{meta['id']}/reindex")
    assert resp.status_code == 200, resp.text
    assert resp.json()["chunk_count"] > 0


def test_reindex_unknown_agent_returns_404(client):
    resp = client.post("/api/agents/does-not-exist/reindex")
    assert resp.status_code == 404


def test_metrics_endpoint_requires_owner_when_secret_set(client, monkeypatch):
    monkeypatch.setenv("OWNER_SECRET", "top-secret")
    from app.config import get_settings

    get_settings.cache_clear()

    resp = client.get("/api/metrics")
    assert resp.status_code == 401

    resp = client.get("/api/metrics", headers={"X-Owner-Secret": "top-secret"})
    assert resp.status_code == 200
