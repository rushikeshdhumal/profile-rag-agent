from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


class LLMError(Exception):
    pass


def llm_configured() -> bool:
    settings = get_settings()
    provider = settings.llm_provider.upper()
    if provider == "OLLAMA":
        return True
    return bool(settings.llm_api_key.strip())


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def chat_completion(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    settings = get_settings()
    if not llm_configured():
        raise LLMError("LLM_API_KEY is not configured")

    base_url = settings.resolve_base_url()
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key or 'ollama'}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }

    with httpx.Client(timeout=90.0) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)

    if response.status_code == 429:
        logger.warning("LLM rate limited (429); retrying")
        raise RateLimitError("Rate limited by LLM provider")

    if response.status_code >= 400:
        detail = response.text[:500]
        logger.error("LLM error %s: %s", response.status_code, detail)
        raise LLMError(f"LLM request failed ({response.status_code}): {detail}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise LLMError(f"Unexpected LLM response shape: {data}") from exc
