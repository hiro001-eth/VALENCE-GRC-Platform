"""Audit findings router: tracks findings remediation state machine workflow."""
import hashlib
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.auth.dependencies import RequireAnalyst, RequireAuditor
from grc_dashboard.db.models import AuditFinding, User
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()


class FindingCreate(BaseModel):
    title: str
    description: str | None = None
    metric_id: str | None = None
    severity: str = "high"  # critical | high | medium | low


class FindingUpdate(BaseModel):
    status: str | None = None
    owner_username: str | None = None
    remediation_plan: str | None = None


@router.get("/")
async def list_findings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = RequireAuditor,
) -> list[dict[str, Any]]:
    """List all findings scoped to the active tenant."""
    tenant_id = request.headers.get("X-Tenant-ID", "default")
    
    result = await db.execute(
        select(AuditFinding)
        .where(AuditFinding.tenant_id == tenant_id)
        .order_by(AuditFinding.created_at.desc())
    )
    findings = result.scalars().all()
    
    # If no findings exist for this tenant, seed 2 default findings (exactly once)
    if not findings:
        seed_data = [
            {
                "title": "Critical CVE Patch Lag Exceeds Threshold",
                "description": "8 critical CVEs remained unpatched for more than 7 days, violating SLA limits.",
                "metric_id": "KRI-CVE-001",
                "severity": "critical",
                "status": "finding",
                "owner_username": None,
                "remediation_plan": None,
            },
            {
                "title": "DLP Policy Violations Spike",
                "description": "Abnormal egress file transfers detected in cloud database assets.",
                "metric_id": "KRI-DLP-001",
                "severity": "high",
                "status": "assigned",
                "owner_username": "analyst",
                "remediation_plan": "Review access controls, update egress threshold levels, and isolate the source database.",
            },
        ]
        for item in seed_data:
            # Deduplicate: skip if a finding with this title already exists for this tenant
            existing_check = await db.execute(
                select(AuditFinding.id).where(
                    AuditFinding.tenant_id == tenant_id,
                    AuditFinding.title == item["title"],
                ).limit(1)
            )
            if existing_check.scalar_one_or_none():
                continue

            db.add(
                AuditFinding(
                    id=f"FIND-2026-{uuid.uuid4().hex[:6].upper()}",
                    tenant_id=tenant_id,
                    **item,
                )
            )
        await db.commit()
        result = await db.execute(
            select(AuditFinding)
            .where(AuditFinding.tenant_id == tenant_id)
            .order_by(AuditFinding.created_at.desc())
        )
        findings = result.scalars().all()
        
    return [
        {
            "id": f.id,
            "tenant_id": f.tenant_id,
            "title": f.title,
            "description": f.description,
            "metric_id": f.metric_id,
            "severity": f.severity,
            "status": f.status,
            "owner_username": f.owner_username,
            "remediation_plan": f.remediation_plan,
            "evidence_file_name": f.evidence_file_name,
            "evidence_hash": f.evidence_hash,
            "evidence_id": f.evidence_id,
            "created_at": f.created_at.isoformat(),
            "updated_at": f.updated_at.isoformat(),
        }
        for f in findings
    ]


@router.post("/")
async def create_finding(
    request: Request,
    body: FindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Create a new audit finding."""
    tenant_id = request.headers.get("X-Tenant-ID", "default")
    finding_id = f"FIND-2026-{uuid.uuid4().hex[:6].upper()}"

    finding = AuditFinding(
        id=finding_id,
        tenant_id=tenant_id,
        title=body.title,
        description=body.description,
        metric_id=body.metric_id,
        severity=body.severity,
        status="finding",
    )
    db.add(finding)
    await db.commit()

    logger.info("finding_created", finding_id=finding_id, tenant_id=tenant_id)
    return {"status": "success", "finding_id": finding_id, "message": "Finding created successfully."}


@router.put("/{finding_id}")
async def update_finding(
    finding_id: str,
    body: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Update owner, status, or remediation plan of an audit finding."""
    result = await db.execute(select(AuditFinding).where(AuditFinding.id == finding_id))
    finding = result.scalar_one_or_none()

    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding '{finding_id}' not found.")

    if body.status:
        finding.status = body.status
    if body.owner_username:
        finding.owner_username = body.owner_username
    if body.remediation_plan:
        finding.remediation_plan = body.remediation_plan

    await db.commit()
    logger.info("finding_updated", finding_id=finding_id, status=finding.status)
    return {"status": "success", "message": "Finding updated successfully."}


@router.post("/{finding_id}/evidence")
async def upload_finding_evidence(
    finding_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Upload evidence to transition a finding to CLOSED status."""
    result = await db.execute(select(AuditFinding).where(AuditFinding.id == finding_id))
    finding = result.scalar_one_or_none()

    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding '{finding_id}' not found.")

    content = await file.read()
    evidence_hash = hashlib.sha256(content).hexdigest()

    # Record in cryptographic Evidence Vault
    vault_record = await append_evidence_record(
        db,
        finding.tenant_id,
        event_type="audit_remediation_evidence",
        category="audit_evidence",
        data={
            "finding_id": finding.id,
            "title": finding.title,
            "filename": file.filename,
            "sha256": evidence_hash,
            "resolved_by": current_user.username,
        },
        run_id="VALENCE_AUDIT",
    )

    finding.evidence_file_name = file.filename
    finding.evidence_hash = evidence_hash
    finding.evidence_id = vault_record["evidence_id"]
    finding.status = "closed"

    await db.commit()
    logger.info("finding_closed_with_evidence", finding_id=finding_id, evidence_id=vault_record["evidence_id"])

    return {
        "status": "success",
        "message": f"Finding '{finding_id}' closed successfully.",
        "evidence_id": vault_record["evidence_id"],
        "evidence_hash": evidence_hash,
    }
