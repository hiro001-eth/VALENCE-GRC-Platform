"""Helpers for resolving per-request tenant metrics from app state."""
from typing import Any

from fastapi import Request


def get_tenant_results(request: Request) -> dict[str, Any]:
    """Return metrics payload for the resolved tenant on this request."""
    results: dict[str, Any] = getattr(request.state, "tenant_results", None) or {}
    if results:
        return results
    tenant_id = getattr(request.state, "tenant_id", "demo-global-hq")
    by_tenant: dict[str, Any] = getattr(request.app.state, "latest_results_by_tenant", {})
    return by_tenant.get(tenant_id, {})


def get_tenant_id(request: Request) -> str:
    return getattr(request.state, "tenant_id", "demo-global-hq")
