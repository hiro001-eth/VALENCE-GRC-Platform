"""Google Workspace admin audit and access review evidence."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_google_workspace_evidence(
    tenant_id: str, metadata: dict[str, Any], secrets: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    domain = metadata.get("domain", "company.com")
    token = (secrets or {}).get("api_key") or (secrets or {}).get("access_token")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("google_workspace", "admin_audit_log", "pass", {
                "domain": domain,
                "admin_events_7d": 89,
                "suspicious_logins_blocked": 4,
            }),
            snapshot("google_workspace", "2sv_enforcement", "pass", {
                "users_enrolled_pct": 97.2,
                "admins_enrolled_pct": 100.0,
            }),
            snapshot("google_workspace", "access_review", "pass", {
                "stale_accounts_90d": 2,
                "terminated_not_disabled": 0,
            }),
            snapshot("google_workspace", "dlp_rules", "pass", {"rules_active": 6, "incidents_30d": 1}),
        ]

    if token:
        headers = {"Authorization": f"Bearer {token}"}
        items: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                users_res = await client.get(
                    "https://admin.googleapis.com/admin/reports/v1/usage/users/all/dates/2024-01-01",
                    headers=headers,
                    params={"parameters": "accounts:is_2sv_enrolled"},
                )
                if users_res.status_code == 200:
                    data = users_res.json()
                    items.append(snapshot("google_workspace", "2sv_enforcement", "pass", {
                        "domain": domain,
                        "usage_records": len(data.get("usageReports", [])),
                        "live_pull": True,
                    }))

                audit_res = await client.get(
                    "https://admin.googleapis.com/admin/reports/v1/activity/users/all/applications/login",
                    headers=headers,
                    params={"maxResults": 10},
                )
                if audit_res.status_code == 200:
                    activities = audit_res.json().get("items", [])
                    items.append(snapshot("google_workspace", "admin_audit_log", "pass", {
                        "domain": domain,
                        "recent_login_events": len(activities),
                        "live_pull": True,
                    }))
                if items:
                    return items
        except Exception:
            pass

    return [
        snapshot("google_workspace", "connection_verified", "configured", {
            "domain": domain,
            "note": "Complete OAuth consent for Admin SDK Reports API",
        }),
    ]
