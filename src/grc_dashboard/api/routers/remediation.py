"""Remediation task workflow — owners, SLAs, deadlines (Vanta/ServiceNow-style)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import IntegrationSettings, RemediationTask, User
from grc_dashboard.db.session import get_db
from grc_dashboard.orchestration.itsm_sync import sync_remediation_to_itsm

router = APIRouter()
_analyzer = ComplianceGapAnalyzer(FrameworkLoader())


class RemediationCreate(BaseModel):
    title: str
    description: str | None = None
    owner: str | None = None
    priority: str = "medium"
    due_date: str | None = None
    framework: str | None = None
    control_id: str | None = None
    finding_id: str | None = None
    sla_hours: int = Field(default=72, ge=1, le=8760)


class RemediationUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: str | None = None
    sla_hours: int | None = None


def _row(t: RemediationTask) -> dict[str, Any]:
    # SQLite returns naive datetimes; normalise before comparing with UTC-aware now()
    _due = t.due_date
    if _due is not None and _due.tzinfo is None:
        _due = _due.replace(tzinfo=UTC)
    overdue = (
        t.status not in ("completed", "cancelled")
        and _due is not None
        and _due < datetime.now(UTC)
    )
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "owner": t.owner,
        "priority": t.priority,
        "status": t.status,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "framework": t.framework,
        "control_id": t.control_id,
        "finding_id": t.finding_id,
        "sla_hours": t.sla_hours,
        "external_ticket_id": t.external_ticket_id,
        "external_ticket_url": t.external_ticket_url,
        "overdue": overdue,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


@router.get("/")
async def list_remediation_tasks(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
    status: str | None = None,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    # Lazy-seed demo remediation tasks on first access
    from grc_dashboard.db.persistence import ensure_demo_remediation
    await ensure_demo_remediation(db, tenant_id)
    query = select(RemediationTask).where(RemediationTask.tenant_id == tenant_id)
    if status:
        query = query.where(RemediationTask.status == status)
    query = query.order_by(RemediationTask.created_at.desc())
    result = await db.execute(query)
    tasks = [_row(t) for t in result.scalars().all()]
    open_tasks = [t for t in tasks if t["status"] not in ("completed", "cancelled")]
    return {
        "tasks": tasks,
        "summary": {
            "total": len(tasks),
            "open": len(open_tasks),
            "overdue": sum(1 for t in open_tasks if t["overdue"]),
            "completed": sum(1 for t in tasks if t["status"] == "completed"),
        },
    }


@router.post("/", status_code=201)
async def create_remediation_task(
    body: RemediationCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    due = None
    if body.due_date:
        due = datetime.fromisoformat(body.due_date.replace("Z", "+00:00"))
    elif body.sla_hours:
        due = datetime.now(UTC) + timedelta(hours=body.sla_hours)

    task = RemediationTask(
        id=f"REM-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=tenant_id,
        title=body.title,
        description=body.description,
        owner=body.owner or current_user.username,
        priority=body.priority,
        status="open",
        due_date=due,
        framework=body.framework,
        control_id=body.control_id,
        finding_id=body.finding_id,
        sla_hours=body.sla_hours,
    )
    db.add(task)
    await db.flush()
    settings_res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = settings_res.scalar_one_or_none()
    ticket = await sync_remediation_to_itsm(db, tenant_id, task, settings)
    await db.commit()
    await db.refresh(task)
    row = _row(task)
    if ticket:
        row["external_ticket_id"] = ticket.external_key
        row["external_ticket_url"] = ticket.url
    return row


@router.patch("/{task_id}")
async def update_remediation_task(
    task_id: str,
    body: RemediationUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(RemediationTask).where(
            RemediationTask.id == task_id,
            RemediationTask.tenant_id == tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Remediation task not found")

    for field in ("title", "description", "owner", "priority", "status", "sla_hours"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(task, field, val)
    if body.due_date:
        task.due_date = datetime.fromisoformat(body.due_date.replace("Z", "+00:00"))
    if body.status == "completed" and not task.completed_at:
        task.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)
    return _row(task)


@router.post("/from-gaps")
async def create_tasks_from_gaps(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
    limit: int = 5,
) -> dict[str, Any]:
    """Auto-create remediation tasks from top compliance gaps (Drata/Vanta auto-remediation)."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics = results.get("metrics", []) if results else []
    created: list[dict[str, Any]] = []

    for fw in FrameworkLoader().list_frameworks()[:3]:
        analysis = _analyzer.analyze_gap(fw, metrics)
        for control in analysis.get("controls", []):
            if control.get("status") in ("Compliant",):
                continue
            if len(created) >= limit:
                break
            title = f"Remediate {fw} {control.get('control_id', '')}: {control.get('title', 'Control gap')[:80]}"
            task = RemediationTask(
                id=f"REM-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=tenant_id,
                title=title,
                description=control.get("gap_reason") or "Compliance gap detected by continuous monitoring.",
                owner=current_user.username,
                priority="critical" if control.get("status") == "Non-Compliant" else "high" if control.get("status") == "At Risk" else "medium",
                status="open",
                due_date=datetime.now(UTC) + timedelta(hours=72),
                framework=fw,
                control_id=control.get("control_id"),
                sla_hours=72,
            )
            db.add(task)
            created.append(_row(task))
        if len(created) >= limit:
            break

    await db.commit()
    return {"created": len(created), "tasks": created}
