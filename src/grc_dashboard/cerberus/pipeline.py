"""CERBERUS — CVE intelligence to risk register pipeline."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from grc_dashboard.db.models import AuditFinding, RiskRegisterEntry
from grc_dashboard.db.session import AsyncSessionLocal
from grc_dashboard.threat_intel.feeds import fetch_cisa_kev_catalog

logger = structlog.get_logger(__name__)


async def run_cerberus_pipeline(
    tenant_id: str,
    run_id: str,
    metrics: list[dict[str, Any]],
) -> int:
    """Correlate CVE exposure metrics with CISA KEV and open risk register items."""
    cve_metric = next((m for m in metrics if m.get("metric_id") == "KRI-CVE-001"), None)
    if not cve_metric:
        return 0

    rag = cve_metric.get("rag_status", "Green")
    if rag not in ("Red", "Amber"):
        return 0

    kev_items, _, _ = await fetch_cisa_kev_catalog()
    top_kev = kev_items[:5] if kev_items else []
    created = 0

    async with AsyncSessionLocal() as session:
        for item in top_kev:
            cve_id = item.get("cve_id") or item.get("cveID", "")
            if not cve_id:
                continue
            existing = await session.execute(
                select(RiskRegisterEntry).where(
                    RiskRegisterEntry.tenant_id == tenant_id,
                    RiskRegisterEntry.cve_id == cve_id,
                    RiskRegisterEntry.status.in_(("open", "mitigating")),
                )
            )
            if existing.scalar_one_or_none():
                continue

            entry_id = f"RISK-{uuid.uuid4().hex[:8].upper()}"
            title = item.get("vulnerability_name") or item.get("title") or cve_id
            severity = "critical" if rag == "Red" else "high"
            entry = RiskRegisterEntry(
                id=entry_id,
                tenant_id=tenant_id,
                cve_id=cve_id,
                title=title,
                severity=severity,
                owner="soc-team",
                status="open",
                source="cerberus",
                metric_id="KRI-CVE-001",
                notes=f"Auto-opened from CERBERUS pipeline (run {run_id})",
            )
            session.add(entry)

            finding_id = f"FIND-{uuid.uuid4().hex[:6].upper()}"
            session.add(
                AuditFinding(
                    id=finding_id,
                    tenant_id=tenant_id,
                    title=f"CVE exposure: {cve_id}",
                    description=f"CERBERUS detected {cve_id} in CISA KEV while patch lag metric is {rag}.",
                    metric_id="KRI-CVE-001",
                    severity=severity,
                    status="assigned",
                    owner_username="soc-team",
                )
            )
            entry.finding_id = finding_id
            created += 1

        if created:
            await session.commit()
            logger.info("cerberus_risks_created", tenant_id=tenant_id, count=created, run_id=run_id)

    return created
