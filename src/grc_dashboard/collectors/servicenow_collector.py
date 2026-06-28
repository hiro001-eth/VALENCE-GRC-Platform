"""ServiceNow incident and CMDB evidence for ITSM compliance."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_servicenow_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    instance = (metadata.get("instance_url") or metadata.get("site_url") or "").rstrip("/")
    table = metadata.get("incident_table", "incident")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("servicenow", "open_incidents", "pass", {
                "instance": instance or "demo.service-now.com",
                "open_p1_p2": 2,
                "overdue": 0,
            }),
            snapshot("servicenow", "sla_compliance", "pass", {
                "breaches_30d": 0,
                "resolution_within_sla_pct": 98.5,
            }),
            snapshot("servicenow", "cmdb_ci_coverage", "pass", {
                "critical_cis_tracked": 142,
                "stale_discovery_30d": 3,
            }),
            snapshot("servicenow", "remediation_linked", "pass", {
                "valence_tickets_30d": 9,
                "bi_directional_sync": True,
            }),
        ]

    token = (secrets or {}).get("api_key") or (secrets or {}).get("access_token")
    user = metadata.get("username") or metadata.get("servicenow_user")
    password = (secrets or {}).get("password") or (secrets or {}).get("secret")
    if instance and (token or (user and password)):
        base = instance if instance.startswith("http") else f"https://{instance}"
        auth = (user, password) if user and password else None
        headers = {"Accept": "application/json"}
        if token and not auth:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.get(
                    f"{base}/api/now/table/{table}",
                    params={
                        "sysparm_query": "active=true^priorityIN1,2",
                        "sysparm_limit": 25,
                    },
                    headers=headers,
                    auth=auth,
                )
                if res.status_code == 200:
                    records = res.json().get("result", [])
                    return [
                        snapshot("servicenow", "open_incidents", "pass", {
                            "instance": base,
                            "open_p1_p2": len(records),
                            "live_pull": True,
                        }),
                    ]
        except Exception:
            pass

    return [
        snapshot("servicenow", "connection_verified", "configured", {
            "instance": instance or "not_set",
            "note": "Connect ServiceNow via OAuth or instance URL + credentials",
        }),
    ]
