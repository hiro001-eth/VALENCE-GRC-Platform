"""Auditor firm marketplace — Vanta/Drata partnership network."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAuditor
from grc_dashboard.db.models import AuditorEngagement, AuditorFirm, User
from grc_dashboard.db.session import get_db

router = APIRouter()

DEMO_FIRMS = [
    ("Schellman & Company", ["SOC2", "ISO27001", "HIPAA"], ["US", "EU"], True, True, 4.9, 285),
    ("A-LIGN", ["SOC2", "ISO27001", "PCI_DSS"], ["US"], True, True, 4.7, 275),
    ("Coalfire", ["FedRAMP", "SOC2", "ISO27001"], ["US"], True, False, 4.6, 320),
    ("BDO Digital", ["SOC2", "ISO27001", "GDPR"], ["US", "EU", "APAC"], True, True, 4.5, 260),
    ("Prescient Assurance", ["SOC2", "ISO27001"], ["US", "EU"], True, False, 4.8, 240),
    ("Insight Assurance", ["SOC2", "HIPAA"], ["US"], True, False, 4.4, 230),
    ("KirkpatrickPrice", ["SOC2", "PCI_DSS", "HIPAA"], ["US"], True, False, 4.6, 250),
    ("Sensiba", ["SOC2", "ISO27001"], ["US"], True, True, 4.5, 255),
]


class EngagementRequest(BaseModel):
    firm_id: str
    framework: str = "SOC2"
    scope_notes: str | None = None
    auditor_contact: str | None = None


async def _ensure_firms(session: AsyncSession) -> None:
    existing = await session.execute(select(AuditorFirm.id).limit(1))
    if existing.scalar_one_or_none():
        return
    for name, specs, regions, soc2, iso, rating, rate in DEMO_FIRMS:
        session.add(AuditorFirm(
            id=f"AUD-{uuid.uuid4().hex[:6].upper()}",
            name=name,
            specializations=specs,
            regions=regions,
            soc2_accredited=soc2,
            iso27001_lead=iso,
            contact_email=f"engagements@{name.lower().replace(' ', '').replace('&', '')}.com",
            rating=rating,
            hourly_rate_usd=rate,
            description=f"Accredited audit firm specializing in {', '.join(specs)}.",
            active=True,
        ))
    await session.commit()


@router.get("/firms")
async def list_auditor_firms(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
    framework: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    await _ensure_firms(db)
    result = await db.execute(select(AuditorFirm).where(AuditorFirm.active.is_(True)))
    firms = []
    for f in result.scalars().all():
        if framework and framework not in (f.specializations or []):
            continue
        if region and region not in (f.regions or []):
            continue
        firms.append({
            "id": f.id,
            "name": f.name,
            "specializations": f.specializations,
            "regions": f.regions,
            "soc2_accredited": f.soc2_accredited,
            "iso27001_lead": f.iso27001_lead,
            "rating": f.rating,
            "hourly_rate_usd": f.hourly_rate_usd,
            "description": f.description,
            "contact_email": f.contact_email,
        })
    return {
        "firms": firms,
        "total": len(firms),
        "note": "VALENCE auditor marketplace connects your evidence vault and auditor portal directly to accredited firms.",
    }


@router.get("/engagements")
async def list_engagements(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(AuditorEngagement, AuditorFirm)
        .join(AuditorFirm, AuditorEngagement.firm_id == AuditorFirm.id)
        .where(AuditorEngagement.tenant_id == tenant_id)
        .order_by(AuditorEngagement.requested_at.desc())
    )
    engagements = []
    for eng, firm in result.all():
        engagements.append({
            "id": eng.id,
            "firm_name": firm.name,
            "framework": eng.framework,
            "status": eng.status,
            "auditor_contact": eng.auditor_contact,
            "scope_notes": eng.scope_notes,
            "requested_at": eng.requested_at.isoformat(),
        })
    return {"engagements": engagements}


@router.post("/engage", status_code=201)
async def request_auditor_engagement(
    body: EngagementRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    firm_res = await db.execute(select(AuditorFirm).where(AuditorFirm.id == body.firm_id))
    firm = firm_res.scalar_one_or_none()
    if not firm:
        raise HTTPException(status_code=404, detail="Auditor firm not found")

    eng = AuditorEngagement(
        id=f"ENG-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=tenant_id,
        firm_id=body.firm_id,
        framework=body.framework,
        status="requested",
        auditor_contact=body.auditor_contact or firm.contact_email,
        scope_notes=body.scope_notes,
    )
    db.add(eng)
    await db.commit()
    return {
        "engagement_id": eng.id,
        "firm_name": firm.name,
        "status": "requested",
        "message": f"Engagement request sent to {firm.name}. They receive read-only auditor portal access upon acceptance.",
    }
