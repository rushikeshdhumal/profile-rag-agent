from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import Settings, get_settings
from app.schemas import AgentMeta


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def agent_dir(agent_id: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.agents_dir / agent_id


def sources_dir(agent_id: str, settings: Settings | None = None) -> Path:
    path = agent_dir(agent_id, settings) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chroma_dir(agent_id: str, settings: Settings | None = None) -> Path:
    path = agent_dir(agent_id, settings) / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path


def meta_path(agent_id: str, settings: Settings | None = None) -> Path:
    return agent_dir(agent_id, settings) / "meta.json"


def load_meta(agent_id: str, settings: Settings | None = None) -> AgentMeta:
    path = meta_path(agent_id, settings)
    if not path.exists():
        raise FileNotFoundError(f"Agent not found: {agent_id}")
    return AgentMeta.model_validate_json(path.read_text(encoding="utf-8"))


def save_meta(meta: AgentMeta, settings: Settings | None = None) -> None:
    path = meta_path(meta.id, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def create_agent_id() -> str:
    return uuid4().hex[:12]


def list_agents(settings: Settings | None = None) -> list[AgentMeta]:
    settings = settings or get_settings()
    agents: list[AgentMeta] = []
    for child in settings.agents_dir.iterdir():
        if child.is_dir() and (child / "meta.json").exists():
            agents.append(load_meta(child.name, settings))
    agents.sort(key=lambda a: a.created_at, reverse=True)
    return agents


def write_source_file(agent_id: str, filename: str, content: str | bytes, settings: Settings | None = None) -> Path:
    dest = sources_dir(agent_id, settings) / filename
    if isinstance(content, bytes):
        dest.write_bytes(content)
    else:
        dest.write_text(content, encoding="utf-8")
    return dest


def write_json_source(agent_id: str, filename: str, payload: dict, settings: Settings | None = None) -> Path:
    return write_source_file(
        agent_id,
        filename,
        json.dumps(payload, indent=2),
        settings,
    )
