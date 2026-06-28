"""Kandji MDM evidence collector and device sync."""
from __future__ import annotations

from typing import Any

import httpx

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot


async def collect_kandji_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    subdomain = metadata.get("subdomain", "yourorg")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("kandji", "blueprint_compliance", "pass", {
                "subdomain": subdomain,
                "devices_compliant": 88,
                "devices_total": 92,
                "live_pull": False,
            }),
            snapshot("kandji", "encryption_check", "pass", {"filevault_pct": 100.0}),
        ]

    token = (secrets or {}).get("api_key", "")
    if token:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(
                    f"https://{subdomain}.api.kandji.io/api/v1/devices",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if res.status_code == 200:
                    devices = res.json()
                    count = len(devices) if isinstance(devices, list) else devices.get("count", 0)
                    return [
                        snapshot("kandji", "device_inventory", "pass", {
                            "devices": count,
                            "live_pull": True,
                        }),
                    ]
        except Exception:
            pass

    return [snapshot("kandji", "connection_verified", "configured", {"subdomain": subdomain})]


async def fetch_kandji_devices(
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if demo_mode_for_tenant(metadata.get("tenant_id", "")):
        return [
            {"device_id": "KND-001", "device_name": "MacBook Air — Design", "owner_email": "design@company.com",
             "platform": "macos", "mdm_enrolled": True, "disk_encrypted": True, "os_version": "14.4", "compliance_status": "compliant"},
        ]

    subdomain = metadata.get("subdomain", "")
    token = (secrets or {}).get("api_key", "")
    if not subdomain or not token:
        return []

    devices: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(
                f"https://{subdomain}.api.kandji.io/api/v1/devices",
                headers={"Authorization": f"Bearer {token}"},
            )
            if res.status_code == 200:
                body = res.json()
                rows = body if isinstance(body, list) else body.get("devices", body.get("results", []))
                for d in rows[:50]:
                    devices.append({
                        "device_id": f"KND-{d.get('device_id', d.get('id', 'x'))}",
                        "device_name": d.get("device_name", d.get("name", "Kandji device")),
                        "owner_email": d.get("email", ""),
                        "platform": d.get("platform", "macos"),
                        "mdm_enrolled": True,
                        "disk_encrypted": d.get("filevault_enabled", True),
                        "os_version": d.get("os_version", ""),
                        "compliance_status": "compliant" if d.get("compliant", True) else "non_compliant",
                    })
    except Exception:
        pass
    return devices
