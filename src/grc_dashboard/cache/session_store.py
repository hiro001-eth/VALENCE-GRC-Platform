"""Short-lived session store — Redis when available, in-memory fallback."""
from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "").strip()
_MAX_MEMORY_ENTRIES = 10_000  # Prevent memory exhaustion when Redis is unavailable
_MAX_REVOKED_TOKENS = 50_000
_memory: dict[str, tuple[str, float]] = {}
_revoked_tokens: dict[str, float] = {}
_redis_client: Any = None
_redis_checked = False

_REVOKE_PREFIX = "valence:revoked:"


def _get_redis() -> Any:
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    if not REDIS_URL:
        return None
    try:
        import redis

        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("redis_session_store_connected")
        return _redis_client
    except Exception as exc:
        logger.warning("redis_unavailable_using_memory", error=str(exc))
        _redis_client = None
        return None


def set_json(key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    body = json.dumps(payload)
    client = _get_redis()
    if client:
        client.setex(key, ttl_seconds, body)
        return
    _memory[key] = (body, time.time() + ttl_seconds)
    _purge_memory()


def get_json(key: str) -> dict[str, Any] | None:
    client = _get_redis()
    if client:
        raw = client.get(key)
        if not raw:
            return None
        client.delete(key)
        return json.loads(raw)
    entry = _memory.pop(key, None)
    if not entry:
        return None
    body, expires_at = entry
    if time.time() > expires_at:
        return None
    return json.loads(body)


def set_value(key: str, value: str, ttl_seconds: int) -> None:
    client = _get_redis()
    if client:
        client.setex(key, ttl_seconds, value)
        return
    _memory[key] = (value, time.time() + ttl_seconds)
    _purge_memory()


def get_value(key: str) -> str | None:
    client = _get_redis()
    if client:
        raw = client.get(key)
        if raw is None:
            return None
        client.delete(key)
        return raw
    entry = _memory.pop(key, None)
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        return None
    return value


def revoke_token_jti(jti: str, ttl_seconds: int) -> None:
    """Blocklist a JWT by jti until natural expiry."""
    if not jti:
        return
    key = f"{_REVOKE_PREFIX}{jti}"
    client = _get_redis()
    if client:
        client.setex(key, max(ttl_seconds, 60), "1")
        return
    _revoked_tokens[jti] = time.time() + max(ttl_seconds, 60)
    _purge_revoked()


def is_token_revoked(jti: str) -> bool:
    if not jti:
        return False
    key = f"{_REVOKE_PREFIX}{jti}"
    client = _get_redis()
    if client:
        return bool(client.get(key))
    expires = _revoked_tokens.get(jti)
    if not expires:
        return False
    if expires <= time.time():
        _revoked_tokens.pop(jti, None)
        return False
    return True


def _purge_memory() -> None:
    now = time.time()
    expired = [k for k, (_, exp) in _memory.items() if exp <= now]
    for key in expired:
        _memory.pop(key, None)
    # LRU eviction if still over cap
    if len(_memory) > _MAX_MEMORY_ENTRIES:
        # Sort by expiry, remove oldest first
        sorted_keys = sorted(_memory, key=lambda k: _memory[k][1])
        for key in sorted_keys[: len(_memory) - _MAX_MEMORY_ENTRIES]:
            _memory.pop(key, None)


def _purge_revoked() -> None:
    now = time.time()
    expired = [k for k, exp in _revoked_tokens.items() if exp <= now]
    for key in expired:
        _revoked_tokens.pop(key, None)
    # LRU eviction if over cap
    if len(_revoked_tokens) > _MAX_REVOKED_TOKENS:
        sorted_keys = sorted(_revoked_tokens, key=lambda k: _revoked_tokens[k])
        for key in sorted_keys[: len(_revoked_tokens) - _MAX_REVOKED_TOKENS]:
            _revoked_tokens.pop(key, None)
