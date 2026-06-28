"""Azure / Microsoft Entra compliance evidence collector."""
from __future__ import annotations

from typing import Any

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_azure_evidence(
    tenant_id: str, metadata: dict[str, Any], secrets: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    subscription = metadata.get("subscription_id", "unknown")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("azure", "defender_secure_score", "pass", {
                "subscription_id": subscription or "sub-demo-001",
                "secure_score_pct": 78.4,
                "recommendations_open": 12,
            }),
            snapshot("azure", "conditional_access", "pass", {
                "policies_enabled": 6,
                "mfa_required_admins": True,
            }),
            snapshot("azure", "sentinel_incidents", "pass", {
                "incidents_7d": 14,
                "mean_time_to_triage_min": 22,
            }),
        ]

    return [
        snapshot("azure", "connection_verified", "configured", {
            "subscription_id": subscription,
            "note": "Register app with SecurityCenter.Read.All for live pulls",
        }),
    ]
