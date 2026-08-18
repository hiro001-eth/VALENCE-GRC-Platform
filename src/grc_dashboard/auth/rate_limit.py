"""Login rate limiting and account lockout (Redis-backed, memory fallback)."""
from __future__ import annotations

import os
import time

import structlog

from grc_dashboard.cache import session_store

logger = structlog.get_logger(__name__)

LOGIN_RATE_LIMIT = int(os.getenv("AUTH_LOGIN_RATE_LIMIT", "10"))
LOGIN_RATE_WINDOW_SEC = int(os.getenv("AUTH_LOGIN_RATE_WINDOW_SEC", "60"))
LOCKOUT_THRESHOLD = int(os.getenv("AUTH_LOCKOUT_THRESHOLD", "5"))
LOCKOUT_DURATION_SEC = int(os.getenv("AUTH_LOCKOUT_DURATION_SEC", "900"))

_PREFIX_IP = "valence:rl:ip:"
_PREFIX_FAIL = "valence:rl:fail:"
_PREFIX_LOCK = "valence:rl:lock:"


_MAX_COUNTER_ENTRIES = 50_000  # Prevent unbounded growth under sustained attack

_memory_counters: dict[str, tuple[int, float]] = {}


def _incr_memory(key: str, ttl_seconds: int) -> int:
    now = time.time()
    # Purge expired entries periodically
    if len(_memory_counters) > _MAX_COUNTER_ENTRIES:
        expired = [k for k, (_, exp) in _memory_counters.items() if exp <= now]
        for k in expired:
            _memory_counters.pop(k, None)
        # If still over, evict oldest
        if len(_memory_counters) > _MAX_COUNTER_ENTRIES:
            sorted_keys = sorted(_memory_counters, key=lambda k: _memory_counters[k][1])
            for k in sorted_keys[:len(_memory_counters) - _MAX_COUNTER_ENTRIES]:
                _memory_counters.pop(k, None)
    entry = _memory_counters.get(key)
    if not entry or entry[1] <= now:
        _memory_counters[key] = (1, now + ttl_seconds)
        return 1
    count = entry[0] + 1
    _memory_counters[key] = (count, entry[1])
    return count


def _get_memory(key: str) -> int | None:
    entry = _memory_counters.get(key)
    if not entry:
        return None
    if entry[1] <= time.time():
        _memory_counters.pop(key, None)
        return None
    return entry[0]


def incr_counter(key: str, ttl_seconds: int) -> int:
    client = session_store._get_redis()  # noqa: SLF001
    if client:
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, ttl_seconds)
        return count
    return _incr_memory(key, ttl_seconds)


def is_ip_rate_limited(client_ip: str) -> bool:
    count = incr_counter(f"{_PREFIX_IP}{client_ip}", LOGIN_RATE_WINDOW_SEC)
    return count > LOGIN_RATE_LIMIT


def is_account_locked(username: str) -> bool:
    client = session_store._get_redis()  # noqa: SLF001
    key = f"{_PREFIX_LOCK}{username.lower()}"
    if client:
        return bool(client.get(key))
    entry = _memory_counters.get(key)
    if not entry:
        return False
    if entry[1] <= time.time():
        _memory_counters.pop(key, None)
        return False
    return True


def record_failed_login(username: str) -> int:
    """Record failure; return remaining attempts before lockout."""
    key = f"{_PREFIX_FAIL}{username.lower()}"
    failures = incr_counter(key, LOCKOUT_DURATION_SEC)
    if failures >= LOCKOUT_THRESHOLD:
        lock_key = f"{_PREFIX_LOCK}{username.lower()}"
        client = session_store._get_redis()  # noqa: SLF001
        if client:
            client.setex(lock_key, LOCKOUT_DURATION_SEC, "1")
        else:
            _memory_counters[lock_key] = (1, time.time() + LOCKOUT_DURATION_SEC)
        logger.warning("account_locked", username=username, failures=failures)
    return max(0, LOCKOUT_THRESHOLD - failures)


def clear_failed_logins(username: str) -> None:
    key = f"{_PREFIX_FAIL}{username.lower()}"
    client = session_store._get_redis()  # noqa: SLF001
    if client:
        client.delete(key, f"{_PREFIX_LOCK}{username.lower()}")
        return
    _memory_counters.pop(key, None)
    _memory_counters.pop(f"{_PREFIX_LOCK}{username.lower()}", None)


def lockout_message(username: str) -> str:
    return (
        f"Account temporarily locked after {LOCKOUT_THRESHOLD} failed attempts. "
        f"Try again in {LOCKOUT_DURATION_SEC // 60} minutes or contact your administrator."
    )


REFRESH_RATE_LIMIT = int(os.getenv("AUTH_REFRESH_RATE_LIMIT", "30"))
REFRESH_RATE_WINDOW_SEC = int(os.getenv("AUTH_REFRESH_RATE_WINDOW_SEC", "60"))
_PREFIX_REFRESH = "valence:rl:refresh:"


def is_refresh_rate_limited(client_ip: str) -> bool:
    count = incr_counter(f"{_PREFIX_REFRESH}{client_ip}", REFRESH_RATE_WINDOW_SEC)
    return count > REFRESH_RATE_LIMIT
