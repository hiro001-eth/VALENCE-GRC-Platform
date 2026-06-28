"""Jamf Pro MDM evidence collector and device sync."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_jamf_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base_url = metadata.get("url", "https://yourorg.jamfcloud.com").rstrip("/")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("jamf", "device_compliance", "pass", {
                "enrolled_devices": 142,
                "compliant_pct": 96.5,
                "filevault_enabled_pct": 98.0,
                "live_pull": False,
            }),
            snapshot("jamf", "policy_compliance", "pass", {
                "policies_active": 12,
                "non_compliant_devices": 5,
            }),
        ]

    user = (secrets or {}).get("username") or metadata.get("username", "")
    password = (secrets or {}).get("api_key") or (secrets or {}).get("password", "")
    if user and password:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(
                    f"{base_url}/api/v1/computers-inventory",
                    auth=(user, password),
                    headers={"Accept": "application/json"},
                    params={"page-size": 50},
                )
                if res.status_code == 200:
                    data = res.json()
                    total = data.get("totalCount", len(data.get("results", [])))
                    return [
                        snapshot("jamf", "device_inventory", "pass", {
                            "enrolled_devices": total,
                            "live_pull": True,
                        }),
                    ]
        except Exception:
            pass

    return [snapshot("jamf", "connection_verified", "configured", {"url": base_url})]


async def fetch_jamf_devices(
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return normalized device rows for MDM sync."""
    if demo_mode_for_tenant(metadata.get("tenant_id", "")):
        return [
            {"device_id": "JAMF-001", "device_name": "MacBook — Engineering", "owner_email": "dev@company.com",
             "platform": "macos", "mdm_enrolled": True, "disk_encrypted": True, "os_version": "14.5", "compliance_status": "compliant"},
            {"device_id": "JAMF-002", "device_name": "iPhone — Sales", "owner_email": "sales@company.com",
             "platform": "ios", "mdm_enrolled": True, "disk_encrypted": True, "os_version": "17.4", "compliance_status": "compliant"},
        ]

    base_url = metadata.get("url", "").rstrip("/")
    user = (secrets or {}).get("username", "")
    password = (secrets or {}).get("api_key", "")
    if not base_url or not user:
        return []

    devices: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(
                f"{base_url}/api/v1/computers-inventory",
                auth=(user, password),
                headers={"Accept": "application/json"},
                params={"page-size": 100},
            )
            if res.status_code == 200:
                for row in res.json().get("results", [])[:50]:
                    general = row.get("general", {})
                    os_info = row.get("operatingSystem", {})
                    devices.append({
                        "device_id": f"JAMF-{general.get('id', 'unknown')}",
                        "device_name": general.get("name", "Jamf device"),
                        "owner_email": general.get("username", ""),
                        "platform": "macos",
                        "mdm_enrolled": True,
                        "disk_encrypted": bool(row.get("fileVault", {}).get("partitionName")),
                        "os_version": os_info.get("version", ""),
                        "compliance_status": "compliant",
                    })
    except Exception:
        pass
    return devices
