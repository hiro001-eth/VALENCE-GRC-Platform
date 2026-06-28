"""Evidence request workflow — auditor assigns, assignee fulfills."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAnalyst, RequireAuditor
from grc_dashboard.db.models import EvidenceRequest, User
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()


class CreateEvidenceRequest(BaseModel):
    framework: str = "SOC2"
    control_id: str
    title: str
    description: str | None = None
    assignee: str | None = None
    due_at: str | None = None


class FulfillEvidenceRequest(BaseModel):
    notes: str | None = None
    artifact_summary: str = "Manual evidence upload"


@router.get("/requests")
async def list_evidence_requests(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
    status: str | None = None,
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id(request)
    query = select(EvidenceRequest).where(EvidenceRequest.tenant_id == tenant_id)
    if status:
        query = query.where(EvidenceRequest.status == status)
    result = await db.execute(query.order_by(EvidenceRequest.created_at.desc()))
    return [
        {
            "id": r.id,
            "framework": r.framework,
            "control_id": r.control_id,
            "title": r.title,
            "description": r.description,
            "requested_by": r.requested_by,
            "assignee": r.assignee,
            "due_at": r.due_at.isoformat() if r.due_at else None,
            "status": r.status,
            "evidence_id": r.evidence_id,
            "created_at": r.created_at.isoformat(),
        }
        for r in result.scalars().all()
    ]


@router.post("/requests", status_code=201)
async def create_evidence_request(
    body: CreateEvidenceRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    req_id = f"EVREQ-{uuid.uuid4().hex[:8].upper()}"
    due_at = None
    if body.due_at:
        due_at = datetime.fromisoformat(body.due_at.replace("Z", "+00:00"))

    row = EvidenceRequest(
        id=req_id,
        tenant_id=tenant_id,
        framework=body.framework.upper(),
        control_id=body.control_id,
        title=body.title,
        description=body.description,
        requested_by=current_user.username,
        assignee=body.assignee,
        due_at=due_at,
        status="pending",
    )
    db.add(row)
    await db.commit()
    logger.info("evidence_request_created", request_id=req_id, control_id=body.control_id)
    return {"id": req_id, "status": "pending"}


@router.post("/requests/{request_id}/fulfill")
async def fulfill_evidence_request(
    request_id: str,
    body: FulfillEvidenceRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(EvidenceRequest).where(
            EvidenceRequest.id == request_id,
            EvidenceRequest.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Evidence request not found")
    if row.status == "fulfilled":
        raise HTTPException(status_code=409, detail="Request already fulfilled")

    vault_record = await append_evidence_record(
        db,
        tenant_id,
        event_type="evidence_request_fulfillment",
        category="audit_evidence",
        data={
            "request_id": request_id,
            "control_id": row.control_id,
            "framework": row.framework,
            "artifact_summary": body.artifact_summary,
            "notes": body.notes,
            "fulfilled_by": current_user.username,
        },
        run_id="VALENCE_EVIDENCE_REQ",
    )
    row.status = "fulfilled"
    row.evidence_id = vault_record["evidence_id"]
    row.updated_at = datetime.now(UTC)
    await db.commit()
    return {"status": "fulfilled", "evidence_id": vault_record["evidence_id"]}
