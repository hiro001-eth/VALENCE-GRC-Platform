"""Live Threat Intelligence — CISA KEV + MITRE ATT&CK STIX correlation."""
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request

from grc_dashboard.api.tenant_context import get_tenant_results
from grc_dashboard.auth.dependencies import require_feature
from grc_dashboard.db.models import User
from grc_dashboard.threat_intel.feeds import (
    correlate_threats,
    fetch_cisa_kev_catalog,
    fetch_mitre_attack_trends,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/")
async def get_threat_intel(
    request: Request,
    current_user: User = Depends(require_feature("threat_intel")),
) -> dict[str, Any]:
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    kev_feed, kev_released, kev_live = await fetch_cisa_kev_catalog()
    mitre_trends, mitre_sync, mitre_live = await fetch_mitre_attack_trends()
    correlations = correlate_threats(kev_feed, mitre_trends, metrics)
    now = datetime.now(UTC)

    critical_count = sum(1 for c in correlations if c["severity"] == "critical")
    high_count = sum(1 for c in correlations if c["severity"] == "high")

    if critical_count >= 2:
        threat_level, threat_color = "SEVERE", "#ef4444"
    elif critical_count >= 1 or high_count >= 3:
        threat_level, threat_color = "HIGH", "#f59e0b"
    elif high_count >= 1:
        threat_level, threat_color = "ELEVATED", "#eab308"
    else:
        threat_level, threat_color = "GUARDED", "#22c55e"

    return {
        "last_updated": now.isoformat(),
        "threat_level": {
            "level": threat_level,
            "color": threat_color,
            "critical_alerts": critical_count,
            "high_alerts": high_count,
        },
        "correlations": correlations,
        "cisa_kev": {
            "total_tracked": len(kev_feed),
            "critical_count": sum(1 for k in kev_feed if k.get("severity") == "CRITICAL"),
            "ransomware_linked": sum(1 for k in kev_feed if k.get("known_ransomware_use")),
            "vulnerabilities": kev_feed,
            "catalog_date_released": kev_released,
            "live_feed": kev_live,
        },
        "mitre_attack_trends": mitre_trends,
        "data_sources": [
            {
                "name": "CISA Known Exploited Vulnerabilities",
                "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                "last_sync": kev_released or now.isoformat(),
                "live": kev_live,
            },
            {
                "name": "MITRE ATT&CK Enterprise STIX",
                "url": "https://attack.mitre.org/",
                "last_sync": mitre_sync,
                "live": mitre_live,
            },
        ],
    }


@router.get("/kev")
async def get_cisa_kev(current_user: User = Depends(require_feature("threat_intel"))) -> dict[str, Any]:
    kev_feed, released, live = await fetch_cisa_kev_catalog()
    return {
        "total": len(kev_feed),
        "catalog_date_released": released,
        "live_feed": live,
        "vulnerabilities": kev_feed,
    }


@router.get("/mitre")
async def get_mitre_trends(current_user: User = Depends(require_feature("threat_intel"))) -> dict[str, Any]:
    trends, synced, live = await fetch_mitre_attack_trends()
    return {"total": len(trends), "last_sync": synced, "live_feed": live, "techniques": trends}
