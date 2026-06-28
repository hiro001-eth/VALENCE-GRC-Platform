"""Shared helpers for integration evidence collectors."""
from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any


def demo_mode_for_tenant(tenant_id: str) -> bool:
    from grc_dashboard.tenancy.constants import is_demo_tenant

    if is_demo_tenant(tenant_id):
        return True
    is_prod = os.getenv("VALENCE_ENV", "development").lower() == "production"
    if is_prod:
        return os.getenv("VALENCE_COLLECTOR_DEMO", "false").lower() in {"1", "true", "yes"}
    return os.getenv("VALENCE_COLLECTOR_DEMO", "true").lower() in {"1", "true", "yes"}


def snapshot(
    integration: str,
    check_name: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": f"{integration}_check",
        "data": {
            "integration": integration,
            "check": check_name,
            "status": status,
            "collected_at": datetime.now(UTC).isoformat(),
            "details": details or {},
        },
    }


def deterministic_score(seed: str, low: float, high: float) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return round(low + (h % 1000) / 1000 * (high - low), 1)
