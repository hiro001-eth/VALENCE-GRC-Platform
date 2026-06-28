"""GitHub organization audit log and branch protection evidence."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_github_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    org = metadata.get("org", "example-org")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("github", "branch_protection", "pass", {
                "org": org,
                "repos_with_protection": 18,
                "repos_total": 22,
                "required_reviews": True,
            }),
            snapshot("github", "secret_scanning", "pass", {"alerts_open": 0, "alerts_resolved_30d": 2}),
            snapshot("github", "org_audit_log", "pass", {
                "events_7d": 340,
                "admin_actions": 12,
                "sso_enforced": True,
            }),
            snapshot("github", "dependabot_alerts", "warn", {"critical_open": 1, "high_open": 3}),
        ]

    token = (secrets or {}).get("api_key") or (secrets or {}).get("pat")
    if token and org:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        items: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                repos_res = await client.get(
                    f"https://api.github.com/orgs/{org}/repos?per_page=100",
                    headers=headers,
                )
                if repos_res.status_code == 200:
                    repos = repos_res.json()
                    protected = 0
                    for repo in repos[:15]:
                        br = await client.get(
                            f"https://api.github.com/repos/{repo['full_name']}/branches/main/protection",
                            headers=headers,
                        )
                        if br.status_code == 200:
                            protected += 1
                    items.append(snapshot("github", "branch_protection", "pass" if protected else "warn", {
                        "org": org,
                        "repos_sampled": min(len(repos), 15),
                        "repos_with_protection": protected,
                        "repos_total": len(repos),
                        "live_pull": True,
                    }))

                org_res = await client.get(f"https://api.github.com/orgs/{org}", headers=headers)
                if org_res.status_code == 200:
                    org_data = org_res.json()
                    items.append(snapshot("github", "org_settings", "pass", {
                        "org": org,
                        "two_factor_requirement_enabled": org_data.get("two_factor_requirement_enabled"),
                        "live_pull": True,
                    }))
                if items:
                    return items
        except Exception:
            pass

    return [
        snapshot("github", "connection_verified", "configured", {
            "org": org,
            "note": "Provide PAT with read:org for live pulls",
        }),
    ]
