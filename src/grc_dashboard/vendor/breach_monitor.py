"""Vendor breach monitoring against public breach intelligence."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.db.models import VendorBreachAlert, VendorRecord

logger = structlog.get_logger(__name__)

# Curated public breach registry (expandable; production can wire HIBP/vendor APIs)
KNOWN_BREACHES: dict[str, dict[str, str]] = {
    "marketing agency": {"date": "2024-11", "severity": "medium", "details": "Email list exposure reported in industry advisory"},
    "cloudhost nepal": {"date": "2025-01", "severity": "high", "details": "Unauthorized API access incident disclosed"},
    "salesforce": {"date": "2023-09", "severity": "low", "details": "Third-party integration token leak (industry-wide)"},
    "okta": {"date": "2023-10", "severity": "medium", "details": "Support system breach — monitor IdP vendor risk"},
}


async def scan_vendor_breaches(session: AsyncSession, tenant_id: str) -> int:
    """Match vendor roster against known breach registry and create alerts."""
    result = await session.execute(
        select(VendorRecord).where(VendorRecord.tenant_id == tenant_id)
    )
    vendors = result.scalars().all()
    created = 0
    for vendor in vendors:
        key = vendor.name.lower().strip()
        breach = KNOWN_BREACHES.get(key)
        if not breach:
            continue
        existing = await session.execute(
            select(VendorBreachAlert.id).where(
                VendorBreachAlert.tenant_id == tenant_id,
                VendorBreachAlert.vendor_name == vendor.name,
                VendorBreachAlert.breach_date == breach["date"],
            )
        )
        if existing.scalar_one_or_none():
            continue
        session.add(
            VendorBreachAlert(
                tenant_id=tenant_id,
                vendor_name=vendor.name,
                breach_source="valence_breach_monitor",
                severity=breach["severity"],
                breach_date=breach["date"],
                details=breach["details"],
            )
        )
        vendor.incident_count = (vendor.incident_count or 0) + 1
        created += 1
    if created:
        await session.commit()
        logger.info("vendor_breach_alerts_created", tenant_id=tenant_id, count=created)
    return created


async def list_breach_alerts(session: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    result = await session.execute(
        select(VendorBreachAlert)
        .where(VendorBreachAlert.tenant_id == tenant_id)
        .order_by(VendorBreachAlert.created_at.desc())
    )
    return [
        {
            "id": a.id,
            "vendor_name": a.vendor_name,
            "breach_source": a.breach_source,
            "severity": a.severity,
            "breach_date": a.breach_date,
            "details": a.details,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat(),
        }
        for a in result.scalars().all()
    ]
