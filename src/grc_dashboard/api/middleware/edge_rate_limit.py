"""API-wide edge rate limiting (complements nginx limit_req)."""
from __future__ import annotations

import os
import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.responses import JSONResponse

from grc_dashboard.auth.jwt_handler import decode_token
from grc_dashboard.cache import session_store

API_RATE_LIMIT = int(os.getenv("VALENCE_API_RATE_LIMIT", "120"))
AUTHENTICATED_API_RATE_LIMIT = int(os.getenv("VALENCE_AUTHENTICATED_API_RATE_LIMIT", "600"))
API_RATE_WINDOW_SEC = int(os.getenv("VALENCE_API_RATE_WINDOW_SEC", "60"))
_PREFIX = "valence:edge:api:"

_memory: dict[str, tuple[int, float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _incr(key: str) -> int:
    client = session_store._get_redis()  # noqa: SLF001
    if client:
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, API_RATE_WINDOW_SEC)
        return count
    now = time.time()
    entry = _memory.get(key)
    if not entry or entry[1] <= now:
        _memory[key] = (1, now + API_RATE_WINDOW_SEC)
        return 1
    count = entry[0] + 1
    _memory[key] = (count, entry[1])
    return count


_SKIP_PREFIXES = (
    "/api/health",
    "/api/status",
    "/api/billing/webhook",
    "/api/scim/",
)


def _rate_limit_subject(request: Request) -> tuple[str, int]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            payload = decode_token(auth_header[7:], check_revoked=False)
        except ValueError:
            pass
        else:
            if payload.get("type") == "access":
                subject = payload.get("sub") or payload.get("tenant_id")
                if subject:
                    return (f"user:{subject}", AUTHENTICATED_API_RATE_LIMIT)
    return (f"ip:{_client_ip(request)}", API_RATE_LIMIT)


async def edge_rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    if os.getenv("VALENCE_EDGE_RATE_LIMIT", "true").lower() in {"0", "false", "no"}:
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api") or any(path.startswith(p) for p in _SKIP_PREFIXES):
        return await call_next(request)

    subject, limit = _rate_limit_subject(request)
    count = _incr(f"{_PREFIX}{subject}")
    if count > limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Retry later."},
            headers={"Retry-After": str(API_RATE_WINDOW_SEC)},
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
    return response
