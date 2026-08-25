from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import Request, Response

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
_request_latency_ms_sum: dict[tuple[str, str], float] = defaultdict(float)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(json_logs: bool = True, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    if json_logs:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Chroma/PostHog SDK mismatch can still emit ERROR logs; silence that logger
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    req_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    token = request_id_ctx.set(req_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)

    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-Id"] = req_id

    path = request.url.path
    _request_counts[(request.method, path, response.status_code)] += 1
    _request_latency_ms_sum[(request.method, path)] += elapsed_ms

    logging.getLogger("app.request").info(
        "%s %s -> %s (%.1fms)", request.method, path, response.status_code, elapsed_ms
    )
    return response


def render_prometheus_text() -> str:
    """Minimal hand-rolled Prometheus text exposition (no prometheus_client dep)."""
    lines = ["# TYPE http_requests_total counter"]
    for (method, path, status_code), count in sorted(_request_counts.items()):
        lines.append(
            f'http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}'
        )
    lines.append("# TYPE http_request_duration_ms_sum counter")
    for (method, path), total in sorted(_request_latency_ms_sum.items()):
        lines.append(f'http_request_duration_ms_sum{{method="{method}",path="{path}"}} {total:.2f}')
    return "\n".join(lines) + "\n"
