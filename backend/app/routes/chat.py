from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.llm import LLMError
from app.rag import answer_question
from app.ratelimit import enforce_chat_rate_limit
from app.schemas import ChatRequest, ChatResponse
from app.store import load_meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    enforce_chat_rate_limit(request, payload.agent_id)

    try:
        meta = load_meta(payload.agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        answer, sources = answer_question(
            agent_id=payload.agent_id,
            message=payload.message,
            history=payload.history,
            display_name=meta.display_name,
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc

    return ChatResponse(answer=answer, sources=sources)
