from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FaqAnswers(BaseModel):
    open_to_relocate: str = ""
    work_authorization: str = ""
    preferred_roles: str = ""
    preferred_locations: str = ""
    notice_period: str = ""
    compensation_notes: str = ""
    other: str = ""


class AgentCreateFields(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    headline: str = ""
    linkedin_url: str = ""
    linkedin_text: str = ""
    github_username: str = ""
    scholar_url: str = ""
    scholar_text: str = ""
    blog_text: str = ""
    faq: FaqAnswers = Field(default_factory=FaqAnswers)


class AgentMeta(BaseModel):
    id: str
    display_name: str
    headline: str = ""
    linkedin_url: str = ""
    github_username: str = ""
    scholar_url: str = ""
    created_at: str
    updated_at: str
    source_count: int = 0
    chunk_count: int = 0


class ChatMessage(BaseModel):
    role: str
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    agent_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_model: str
    llm_configured: bool
    public_chat_only: bool
    owner_auth_required: bool
