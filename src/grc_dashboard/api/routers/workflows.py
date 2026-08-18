"""Multi-business-unit workflow designer — MetricStream-style governance."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst
from grc_dashboard.db.models import BusinessUnit, ChangeRequest, User, WorkflowDefinition
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

router = APIRouter()

DEFAULT_WORKFLOWS = [
    {
        "name": "SOC 2 evidence collection",
        "trigger": "scheduled",
        "description": "Monthly evidence pull from SIEM + cloud integrations",
        "steps": [
            {"id": "s1", "type": "collect_evidence", "label": "Run pipeline", "owner_role": "analyst"},
            {"id": "s2", "type": "map_controls", "label": "Map to TSC controls", "owner_role": "grc"},
            {"id": "s3", "type": "auditor_review", "label": "Auditor sign-off", "owner_role": "auditor"},
        ],
    },
    {
        "name": "Critical finding escalation",
        "trigger": "metric_red",
        "description": "Auto-create remediation + ITSM ticket on Red metrics",
        "steps": [
            {"id": "s1", "type": "create_finding", "label": "Log audit finding", "owner_role": "soc"},
            {"id": "s2", "type": "create_remediation", "label": "Assign remediation task", "owner_role": "ciso"},
            {"id": "s3", "type": "itsm_sync", "label": "Sync to Jira/ServiceNow", "owner_role": "analyst"},
            {"id": "s4", "type": "notify", "label": "Alert CISO channel", "owner_role": "system"},
        ],
    },
]


class BusinessUnitCreate(BaseModel):
    name: str
    code: str = ""
    region: str = ""
    owner: str | None = None
    parent_bu_id: str | None = None


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    bu_id: str | None = None
    trigger: str = "manual"
    steps: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = None
    active: bool | None = None


class ChangeRequestCreate(BaseModel):
    title: str
    description: str | None = None
    bu_id: str | None = None
    change_type: str = "application"
    risk_level: str = "medium"
    planned_start_at: str | None = None
    planned_end_at: str | None = None


class ChangeRequestImplement(BaseModel):
    implementation_notes: str | None = None


async def _ensure_demo_bus(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(BusinessUnit.id).where(BusinessUnit.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return
    for name, code, region in [
        ("Global HQ", "HQ", "US"),
        ("EMEA Operations", "EMEA", "EU"),
        ("APAC Engineering", "APAC", "APAC"),
    ]:
        session.add(BusinessUnit(
            id=f"BU-{uuid.uuid4().hex[:6].upper()}",
            tenant_id=tenant_id,
            name=name,
            code=code,
            region=region,
            owner="ciso",
        ))
    await session.commit()


async def _ensure_demo_workflows(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(WorkflowDefinition.id).where(WorkflowDefinition.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return
    for wf in DEFAULT_WORKFLOWS:
        session.add(WorkflowDefinition(
            id=f"WF-{uuid.uuid4().hex[:6].upper()}",
            tenant_id=tenant_id,
            name=wf["name"],
            description=wf["description"],
            trigger=wf["trigger"],
            steps=wf["steps"],
            active=True,
            created_by="system",
        ))
    await session.commit()


@router.get("/business-units")
async def list_business_units(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_bus(db, tenant_id)
    result = await db.execute(
        select(BusinessUnit).where(BusinessUnit.tenant_id == tenant_id).order_by(BusinessUnit.name)
    )
    units = [
        {"id": u.id, "name": u.name, "code": u.code, "region": u.region, "owner": u.owner, "parent_bu_id": u.parent_bu_id}
        for u in result.scalars().all()
    ]
    return {"business_units": units, "total": len(units)}


@router.post("/business-units", status_code=201)
async def create_business_unit(
    body: BusinessUnitCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    bu = BusinessUnit(
        id=f"BU-{uuid.uuid4().hex[:6].upper()}",
        tenant_id=tenant_id,
        name=body.name,
        code=body.code,
        region=body.region,
        owner=body.owner or current_user.username,
        parent_bu_id=body.parent_bu_id,
    )
    db.add(bu)
    await db.commit()
    return {"id": bu.id, "name": bu.name}


@router.get("/definitions")
async def list_workflows(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
    bu_id: str | None = None,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_workflows(db, tenant_id)
    query = select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == tenant_id)
    if bu_id:
        query = query.where(WorkflowDefinition.bu_id == bu_id)
    result = await db.execute(query.order_by(WorkflowDefinition.name))
    workflows = [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "trigger": w.trigger,
            "steps": w.steps,
            "active": w.active,
            "bu_id": w.bu_id,
            "step_count": len(w.steps or []),
        }
        for w in result.scalars().all()
    ]
    return {"workflows": workflows, "total": len(workflows)}


@router.post("/definitions", status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    wf = WorkflowDefinition(
        id=f"WF-{uuid.uuid4().hex[:6].upper()}",
        tenant_id=tenant_id,
        bu_id=body.bu_id,
        name=body.name,
        description=body.description,
        trigger=body.trigger,
        steps=body.steps,
        active=True,
        created_by=current_user.username,
    )
    db.add(wf)
    await db.commit()
    return {"id": wf.id, "name": wf.name, "steps": wf.steps}


@router.patch("/definitions/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.tenant_id == tenant_id,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.steps is not None:
        wf.steps = body.steps
    if body.active is not None:
        wf.active = body.active
    await db.commit()
    return {"id": wf.id, "name": wf.name, "steps": wf.steps, "active": wf.active}


@router.post("/definitions/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.tenant_id == tenant_id,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    executed = []
    for step in wf.steps or []:
        executed.append({
            "step_id": step.get("id"),
            "type": step.get("type"),
            "label": step.get("label"),
            "status": "completed",
            "note": f"Simulated execution for {step.get('type')} — wire to pipeline/ITSM in production.",
        })
    return {
        "workflow_id": wf.id,
        "workflow_name": wf.name,
        "executed_steps": executed,
        "status": "completed",
    }


@router.get("/change-requests")
async def list_change_requests(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
    status: str | None = None,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    q = select(ChangeRequest).where(ChangeRequest.tenant_id == tenant_id)
    if status:
        q = q.where(ChangeRequest.status == status)
    res = await db.execute(q.order_by(ChangeRequest.created_at.desc()))
    rows = res.scalars().all()
    items = [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "change_type": c.change_type,
            "risk_level": c.risk_level,
            "status": c.status,
            "requested_by": c.requested_by,
            "approved_by": c.approved_by,
            "implemented_by": c.implemented_by,
            "implementation_notes": c.implementation_notes,
            "external_ticket_id": c.external_ticket_id,
            "external_ticket_url": c.external_ticket_url,
            "planned_start_at": c.planned_start_at.isoformat() if c.planned_start_at else None,
            "planned_end_at": c.planned_end_at.isoformat() if c.planned_end_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]
    return {"change_requests": items, "total": len(items)}


@router.post("/change-requests", status_code=201)
async def create_change_request(
    body: ChangeRequestCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    from datetime import UTC, datetime

    tenant_id = get_tenant_id(request)
    start_at = datetime.fromisoformat(body.planned_start_at) if body.planned_start_at else None
    end_at = datetime.fromisoformat(body.planned_end_at) if body.planned_end_at else None
    change = ChangeRequest(
        id=f"CR-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=tenant_id,
        bu_id=body.bu_id,
        title=body.title,
        description=body.description,
        change_type=body.change_type,
        risk_level=body.risk_level,
        status="pending_approval",
        requested_by=current_user.username,
        planned_start_at=start_at,
        planned_end_at=end_at,
        external_ticket_id=f"CHG-{uuid.uuid4().hex[:6].upper()}",
        external_ticket_url="https://itsm.example.com/change/demo",
    )
    db.add(change)
    await db.commit()
    return {
        "id": change.id,
        "status": change.status,
        "requested_by": change.requested_by,
        "created_at": datetime.now(UTC).isoformat(),
    }


@router.post("/change-requests/{change_id}/approve")
async def approve_change_request(
    change_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    res = await db.execute(
        select(ChangeRequest).where(
            ChangeRequest.id == change_id,
            ChangeRequest.tenant_id == tenant_id,
        )
    )
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Change request not found")
    if row.status in {"implemented", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Cannot approve request in status {row.status}")
    row.status = "approved"
    row.approved_by = current_user.username
    await db.commit()
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by}


@router.post("/change-requests/{change_id}/implement")
async def implement_change_request(
    change_id: str,
    body: ChangeRequestImplement,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    res = await db.execute(
        select(ChangeRequest).where(
            ChangeRequest.id == change_id,
            ChangeRequest.tenant_id == tenant_id,
        )
    )
    row = res.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Change request not found")
    if row.status not in {"approved", "implementing"}:
        raise HTTPException(status_code=400, detail="Approve change request before implementation")
    row.status = "implemented"
    row.implemented_by = current_user.username
    if body.implementation_notes is not None:
        row.implementation_notes = body.implementation_notes
    await db.commit()
    return {"id": row.id, "status": row.status, "implemented_by": row.implemented_by}
