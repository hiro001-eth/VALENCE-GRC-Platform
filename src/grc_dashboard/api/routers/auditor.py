"""Consolidated auditor workspace — read-only compliance dashboard."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.routers import compliance as compliance_router
from grc_dashboard.api.routers import policies as policies_router
from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAuditor
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import (
    AuditFinding,
    EvidenceRecord,
    EvidenceRequest,
    PolicyAttestation,
    PolicyRecord,
    ReportRecord,
    User,
)
from grc_dashboard.db.session import get_db

router = APIRouter()
_loader = FrameworkLoader()
_analyzer = ComplianceGapAnalyzer(_loader)


@router.get("/dashboard")
async def auditor_dashboard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Single-pane view for external auditors: readiness, open requests, findings, evidence."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics = results.get("metrics", [])

    readiness = await compliance_router.get_readiness_overview(request, current_user)
    frameworks_detail = []
    for fw in _loader.list_frameworks():
        analysis = _analyzer.analyze_gap(fw, metrics)
        frameworks_detail.append({
            "framework": fw,
            "compliant": analysis.get("compliant", 0),
            "gaps": analysis.get("non_compliant", 0) + analysis.get("at_risk", 0),
            "total": analysis.get("total_controls", 0),
        })

    open_requests = await db.execute(
        select(EvidenceRequest).where(
            EvidenceRequest.tenant_id == tenant_id,
            EvidenceRequest.status.in_(("pending", "in_progress")),
        )
    )
    findings = await db.execute(
        select(AuditFinding).where(
            AuditFinding.tenant_id == tenant_id,
            AuditFinding.status != "closed",
        )
    )
    evidence_count = await db.execute(
        select(func.count()).select_from(EvidenceRecord).where(EvidenceRecord.tenant_id == tenant_id)
    )
    reports = await db.execute(
        select(ReportRecord)
        .where(ReportRecord.tenant_id == tenant_id)
        .order_by(ReportRecord.generated_at.desc())
        .limit(5)
    )
    await policies_router._ensure_demo_policies(db, tenant_id)
    policy_count = await db.execute(
        select(func.count()).select_from(PolicyRecord).where(PolicyRecord.tenant_id == tenant_id)
    )
    attestation_count = await db.execute(
        select(func.count()).select_from(PolicyAttestation).where(PolicyAttestation.tenant_id == tenant_id)
    )

    return {
        "tenant_id": tenant_id,
        "auditor": current_user.username,
        "readiness": readiness,
        "frameworks": frameworks_detail,
        "open_evidence_requests": [
            {
                "id": r.id,
                "framework": r.framework,
                "control_id": r.control_id,
                "title": r.title,
                "status": r.status,
                "due_at": r.due_at.isoformat() if r.due_at else None,
            }
            for r in open_requests.scalars().all()
        ],
        "open_findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
                "owner": f.owner_username,
            }
            for f in findings.scalars().all()
        ],
        "evidence_vault_count": evidence_count.scalar() or 0,
        "policy_library_count": policy_count.scalar() or 0,
        "attestation_count": attestation_count.scalar() or 0,
        "recent_reports": [
            {
                "run_id": r.run_id,
                "generated_at": r.generated_at.isoformat(),
                "metric_count": r.metric_count,
            }
            for r in reports.scalars().all()
        ],
        "access_scope": "read_only",
    }
