"""Global search across GRC entities."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import (
    AuditFinding,
    EvidenceRecord,
    PolicyRecord,
    RemediationTask,
    User,
    VendorRecord,
)
from grc_dashboard.db.session import get_db

router = APIRouter()


@router.get("/")
async def global_search(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
    q: str = Query(..., min_length=2),
    limit: int = Query(20, le=50),
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    term = f"%{q.lower()}%"

    results: list[dict[str, Any]] = []

    findings = await db.execute(
        select(AuditFinding).where(
            AuditFinding.tenant_id == tenant_id,
            or_(
                AuditFinding.title.ilike(term),
                AuditFinding.description.ilike(term),
            ),
        ).limit(8)
    )
    for f in findings.scalars().all():
        results.append({
            "type": "finding",
            "id": f.id,
            "title": f.title,
            "subtitle": f.status,
            "navigate": "findings",
        })

    evidence = await db.execute(
        select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == tenant_id,
            or_(
                EvidenceRecord.event_type.ilike(term),
                EvidenceRecord.category.ilike(term),
            ),
        ).limit(8)
    )
    for e in evidence.scalars().all():
        results.append({
            "type": "evidence",
            "id": e.id,
            "title": e.event_type or "Evidence",
            "subtitle": e.category,
            "navigate": "evidence",
        })

    policies = await db.execute(
        select(PolicyRecord).where(
            PolicyRecord.tenant_id == tenant_id,
            PolicyRecord.title.ilike(term),
        ).limit(6)
    )
    for p in policies.scalars().all():
        results.append({
            "type": "policy",
            "id": p.id,
            "title": p.title,
            "subtitle": p.category,
            "navigate": "policies",
        })

    tasks = await db.execute(
        select(RemediationTask).where(
            RemediationTask.tenant_id == tenant_id,
            RemediationTask.title.ilike(term),
        ).limit(6)
    )
    for t in tasks.scalars().all():
        results.append({
            "type": "remediation",
            "id": t.id,
            "title": t.title,
            "subtitle": t.status,
            "navigate": "compliance",
        })

    vendors = await db.execute(
        select(VendorRecord).where(
            VendorRecord.tenant_id == tenant_id,
            VendorRecord.name.ilike(term),
        ).limit(6)
    )
    for v in vendors.scalars().all():
        results.append({
            "type": "vendor",
            "id": str(v.id),
            "title": v.name,
            "subtitle": f"Risk {v.risk_score}",
            "navigate": "vendors",
        })

    return {"query": q, "results": results[:limit], "total": len(results[:limit])}
