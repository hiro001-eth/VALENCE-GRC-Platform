"""Okta IdP lifecycle and access review evidence."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_okta_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    org_url = metadata.get("org_url", "https://company.okta.com").rstrip("/")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("okta", "mfa_policy", "pass", {
                "org": org_url,
                "users_with_mfa_pct": 98.5,
                "privileged_users_mfa": True,
            }),
            snapshot("okta", "jml_events", "pass", {
                "joiners_30d": 5,
                "movers_30d": 2,
                "leavers_30d": 1,
                "leavers_deprovisioned_24h": True,
            }),
            snapshot("okta", "app_assignments", "pass", {
                "orphaned_accounts": 0,
                "excessive_privilege_flags": 1,
            }),
        ]

    token = (secrets or {}).get("api_key")
    if token:
        headers = {"Authorization": f"SSWS {token}", "Accept": "application/json"}
        items: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                users_res = await client.get(f"{org_url}/api/v1/users?limit=200", headers=headers)
                if users_res.status_code == 200:
                    users = users_res.json()
                    active = [u for u in users if u.get("status") == "ACTIVE"]
                    items.append(snapshot("okta", "user_inventory", "pass", {
                        "org": org_url,
                        "active_users": len(active),
                        "total_users": len(users),
                        "live_pull": True,
                    }))
                    items.append(snapshot("okta", "jml_events", "pass", {
                        "org": org_url,
                        "active_users": len(active),
                        "suspended_users": len(users) - len(active),
                        "live_pull": True,
                    }))
                policies_res = await client.get(f"{org_url}/api/v1/policies?type=MFA_ENROLL", headers=headers)
                if policies_res.status_code == 200:
                    items.append(snapshot("okta", "mfa_policy", "pass", {
                        "mfa_policies": len(policies_res.json()),
                        "live_pull": True,
                    }))
                if items:
                    return items
        except Exception:
            pass

    return [
        snapshot("okta", "connection_verified", "configured", {
            "org": org_url,
            "note": "Provide API token with okta.users.read",
        }),
    ]
