"""HR / IdP joiner-mover-leaver lifecycle evidence."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst
from grc_dashboard.db.models import IntegrationSettings, PersonnelEvent, User
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

router = APIRouter()

DEMO_JML = [
    ("joiner", "alex.chen@company.com", "Alex Chen", "Engineering", "okta"),
    ("joiner", "sam.patel@company.com", "Sam Patel", "Finance", "google_workspace"),
    ("mover", "jordan.lee@company.com", "Jordan Lee", "Security", "manual"),
    ("leaver", "taylor.kim@company.com", "Taylor Kim", "Marketing", "okta"),
]


class JMLEventCreate(BaseModel):
    event_type: Literal["joiner", "mover", "leaver"]
    employee_email: str
    employee_name: str = ""
    department: str = ""
    source: str = "manual"
    notes: str | None = None


async def _ensure_demo_jml(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(PersonnelEvent.id).where(PersonnelEvent.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return
    for i, (etype, email, name, dept, source) in enumerate(DEMO_JML):
        reviewed = etype != "leaver" or i % 2 == 0
        session.add(
            PersonnelEvent(
                id=f"JML-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=tenant_id,
                event_type=etype,
                employee_email=email,
                employee_name=name,
                department=dept,
                source=source,
                access_reviewed=reviewed,
                reviewed_by="analyst" if reviewed else None,
                reviewed_at=datetime.now(UTC) if reviewed else None,
            )
        )
    await session.commit()


def _row(e: PersonnelEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "employee_email": e.employee_email,
        "employee_name": e.employee_name,
        "department": e.department,
        "source": e.source,
        "access_reviewed": e.access_reviewed,
        "reviewed_by": e.reviewed_by,
        "reviewed_at": e.reviewed_at.isoformat() if e.reviewed_at else None,
        "notes": e.notes,
        "created_at": e.created_at.isoformat(),
    }


@router.get("/")
async def list_jml_events(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_jml(db, tenant_id)
    result = await db.execute(
        select(PersonnelEvent)
        .where(PersonnelEvent.tenant_id == tenant_id)
        .order_by(PersonnelEvent.created_at.desc())
    )
    return [_row(e) for e in result.scalars().all()]


@router.get("/summary")
async def jml_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    events = await list_jml_events(request, db, current_user)
    by_type = {"joiner": 0, "mover": 0, "leaver": 0}
    pending_review = 0
    for e in events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
        if not e["access_reviewed"]:
            pending_review += 1
    return {
        "total_events": len(events),
        "by_type": by_type,
        "pending_access_review": pending_review,
        "sla_met_pct": round(
            ((len(events) - pending_review) / len(events)) * 100, 1
        ) if events else 100.0,
    }


@router.post("/", status_code=201)
async def create_jml_event(
    body: JMLEventCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    event_id = f"JML-{uuid.uuid4().hex[:8].upper()}"
    row = PersonnelEvent(
        id=event_id,
        tenant_id=tenant_id,
        event_type=body.event_type,
        employee_email=body.employee_email.strip().lower(),
        employee_name=body.employee_name,
        department=body.department,
        source=body.source,
        notes=body.notes,
    )
    db.add(row)
    await append_evidence_record(
        db,
        tenant_id,
        event_type="personnel_lifecycle",
        category="identity_evidence",
        data={
            "event_id": event_id,
            "event_type": body.event_type,
            "employee_email": body.employee_email,
            "source": body.source,
        },
        run_id="JML",
    )
    await db.commit()
    return _row(row)


@router.post("/sync")
async def sync_personnel_from_idp(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    """Pull JML events from connected Okta integration."""
    from grc_dashboard.personnel.sync import sync_jml_from_integrations

    tenant_id = get_tenant_id(request)
    settings = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    integration = settings.scalar_one_or_none()
    connected = (integration.connected_integrations if integration else None) or {}
    count = await sync_jml_from_integrations(db, tenant_id, connected)
    return {"status": "success", "events_synced": count}


@router.post("/{event_id}/review")
async def review_jml_access(
    event_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(PersonnelEvent).where(
            PersonnelEvent.id == event_id,
            PersonnelEvent.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    row.access_reviewed = True
    row.reviewed_by = current_user.username
    row.reviewed_at = datetime.now(UTC)
    await db.commit()
    return _row(row)
