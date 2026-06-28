"""GCP security posture evidence collector."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_gcp_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    project_id = metadata.get("project_id", "unknown")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("gcp", "security_command_center", "pass", {
                "project_id": project_id or "meridian-prod",
                "active_findings": 8,
                "critical_findings": 0,
            }),
            snapshot("gcp", "iam_no_service_account_keys", "pass", {
                "user_managed_keys": 0,
                "admin_accounts": 3,
            }),
            snapshot("gcp", "cloud_armor_enabled", "pass", {"policies": 2}),
        ]

    api_key = (secrets or {}).get("api_key")
    if api_key and project_id != "unknown":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(
                    f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if res.status_code == 200:
                    return [
                        snapshot("gcp", "project_access_verified", "pass", {
                            "project_id": project_id,
                            "project_name": res.json().get("name"),
                            "live_pull": True,
                        }),
                    ]
        except Exception:
            pass

    return [
        snapshot("gcp", "connection_verified", "configured", {
            "project_id": project_id,
            "note": "Provide OAuth access token or service account with Security Center read",
        }),
    ]
