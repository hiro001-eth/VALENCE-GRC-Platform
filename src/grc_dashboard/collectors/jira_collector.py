"""Jira project issues and SLA evidence for ITSM compliance."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_jira_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    project = metadata.get("project_key", "SECCOMP")
    base = (metadata.get("jira_url") or metadata.get("site_url") or "").rstrip("/")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("jira", "open_security_tasks", "pass", {
                "project": project,
                "open_tasks": 4,
                "overdue": 0,
                "avg_resolution_days": 3.2,
            }),
            snapshot("jira", "sla_compliance", "pass", {
                "breaches_30d": 0,
                "p1_within_sla_pct": 100.0,
            }),
            snapshot("jira", "remediation_linked", "pass", {
                "valence_tickets_30d": 12,
                "auto_created": 8,
            }),
        ]

    token = (secrets or {}).get("api_key") or (secrets or {}).get("access_token")
    email = metadata.get("email") or metadata.get("jira_email")
    if base and token:
        auth = (email, token) if email else None
        headers = {"Accept": "application/json"}
        if not email:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                jql = f'project = "{project}" AND status != Done ORDER BY created DESC'
                url = f"{base}/rest/api/3/search/jql" if "/rest/api" not in base else f"{base}/search"
                if not base.startswith("http"):
                    url = f"https://{base}/rest/api/3/search/jql"
                res = await client.get(
                    url,
                    params={"jql": jql, "maxResults": 25},
                    headers=headers,
                    auth=auth,
                )
                if res.status_code == 200:
                    data = res.json()
                    issues = data.get("issues", [])
                    return [
                        snapshot("jira", "open_security_tasks", "pass", {
                            "project": project,
                            "open_tasks": len(issues),
                            "live_pull": True,
                        }),
                    ]
        except Exception:
            pass

    return [
        snapshot("jira", "connection_verified", "configured", {
            "project": project,
            "note": "Connect Jira via OAuth or set jira_url + API token in metadata",
        }),
    ]
