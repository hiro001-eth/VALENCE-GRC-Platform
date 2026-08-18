"""SENTINEL vendor risk management API."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import User, VendorRecord
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant
from grc_dashboard.vendor.sentinel_scorer import score_vendor

logger = structlog.get_logger(__name__)
router = APIRouter()

DEMO_VENDORS = [
    {"name": "CloudHost Nepal", "tier": "strategic", "questionnaire_score": 62, "data_classification": "confidential", "incident_count": 1, "contract_sla_score": 75},
    {"name": "PayFlow Payments", "tier": "strategic", "questionnaire_score": 88, "data_classification": "restricted", "incident_count": 0, "contract_sla_score": 92},
    {"name": "DevTools SaaS", "tier": "operational", "questionnaire_score": 71, "data_classification": "internal", "incident_count": 2, "contract_sla_score": 68},
    {"name": "Logistics Partner Co", "tier": "operational", "questionnaire_score": 80, "data_classification": "internal", "incident_count": 0, "contract_sla_score": 85},
    {"name": "Marketing Agency", "tier": "low", "questionnaire_score": 55, "data_classification": "public", "incident_count": 3, "contract_sla_score": 60},
]


class VendorCreate(BaseModel):
    name: str
    tier: str = "operational"
    questionnaire_score: float = Field(ge=0, le=100, default=70)
    data_classification: str = "internal"
    incident_count: int = Field(ge=0, default=0)
    contract_sla_score: float = Field(ge=0, le=100, default=80)


async def _ensure_demo_vendors(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    for v in DEMO_VENDORS:
        existing = await session.execute(
            select(VendorRecord.id).where(
                VendorRecord.tenant_id == tenant_id,
                VendorRecord.name == v["name"]
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue
        scored = score_vendor(
            v["questionnaire_score"],
            v["data_classification"],
            v["incident_count"],
            v["contract_sla_score"],
            v["tier"],
        )
        session.add(
            VendorRecord(
                tenant_id=tenant_id,
                name=v["name"],
                tier=v["tier"],
                questionnaire_score=v["questionnaire_score"],
                data_classification=v["data_classification"],
                incident_count=v["incident_count"],
                contract_sla_score=v["contract_sla_score"],
                risk_score=scored["risk_score"],
                risk_tier=scored["risk_tier"],
                last_review_at=datetime.now(UTC),
            )
        )
    await session.commit()


def _vendor_row(v: VendorRecord) -> dict[str, Any]:
    return {
        "id": v.id,
        "name": v.name,
        "tier": v.tier,
        "questionnaire_score": v.questionnaire_score,
        "data_classification": v.data_classification,
        "incident_count": v.incident_count,
        "contract_sla_score": v.contract_sla_score,
        "risk_score": v.risk_score,
        "risk_tier": v.risk_tier,
        "last_review_at": v.last_review_at.isoformat() if v.last_review_at else None,
        "questionnaire_completed": bool(v.questionnaire_responses),
        "questionnaire_score_computed": (
            v.questionnaire_responses.get("computed_score") if v.questionnaire_responses else None
        ),
    }


@router.get("/")
async def list_vendors(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_vendors(db, tenant_id)
    result = await db.execute(
        select(VendorRecord).where(VendorRecord.tenant_id == tenant_id).order_by(VendorRecord.risk_score.desc())
    )
    return [_vendor_row(v) for v in result.scalars().all()]


@router.get("/summary")
async def vendor_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    vendors = await list_vendors(request, db, current_user)
    tiers = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in vendors:
        tiers[v["risk_tier"]] = tiers.get(v["risk_tier"], 0) + 1
    avg = round(sum(v["risk_score"] for v in vendors) / len(vendors), 1) if vendors else 0
    return {"total_vendors": len(vendors), "average_risk_score": avg, "by_tier": tiers}


@router.post("/", status_code=201)
async def create_vendor(
    body: VendorCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    scored = score_vendor(
        body.questionnaire_score,
        body.data_classification,
        body.incident_count,
        body.contract_sla_score,
        body.tier,
    )
    row = VendorRecord(
        tenant_id=tenant_id,
        name=body.name.strip(),
        tier=body.tier,
        questionnaire_score=body.questionnaire_score,
        data_classification=body.data_classification,
        incident_count=body.incident_count,
        contract_sla_score=body.contract_sla_score,
        risk_score=scored["risk_score"],
        risk_tier=scored["risk_tier"],
        last_review_at=datetime.now(UTC),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _vendor_row(row)


@router.post("/{vendor_id}/rescore")
async def rescore_vendor(
    vendor_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(VendorRecord).where(VendorRecord.id == vendor_id, VendorRecord.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")
    scored = score_vendor(
        row.questionnaire_score,
        row.data_classification,
        row.incident_count,
        row.contract_sla_score,
        row.tier,
    )
    row.risk_score = scored["risk_score"]
    row.risk_tier = scored["risk_tier"]
    row.last_review_at = datetime.now(UTC)
    await db.commit()
    return {**_vendor_row(row), "components": scored["components"]}


@router.get("/questionnaire/template")
async def vendor_questionnaire_template(current_user: User = RequireAnalyst) -> dict[str, Any]:
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[4] / "rules" / "vendor_questionnaire.yaml"
    if not path.exists():
        return {"questions": []}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {"name": data.get("name", "SIG Lite"), "questions": data.get("questions", [])}


@router.get("/{vendor_id}/questionnaire")
async def get_vendor_questionnaire(
    vendor_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(VendorRecord).where(VendorRecord.id == vendor_id, VendorRecord.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {
        "vendor_id": vendor_id,
        "vendor_name": row.name,
        "responses": row.questionnaire_responses or {},
        "questionnaire_score": row.questionnaire_score,
    }


@router.post("/{vendor_id}/questionnaire")
async def submit_vendor_questionnaire(
    vendor_id: int,
    body: dict[str, Any],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(VendorRecord).where(VendorRecord.id == vendor_id, VendorRecord.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")

    responses = body.get("responses", body)
    yes_count = sum(1 for v in responses.values() if str(v).lower() in ("yes", "true", "pass"))
    total = max(len(responses), 1)
    computed = round((yes_count / total) * 100, 1)
    row.questionnaire_responses = {**responses, "computed_score": computed, "submitted_by": current_user.username}
    row.questionnaire_score = computed
    scored = score_vendor(
        row.questionnaire_score,
        row.data_classification,
        row.incident_count,
        row.contract_sla_score,
        row.tier,
    )
    row.risk_score = scored["risk_score"]
    row.risk_tier = scored["risk_tier"]
    row.last_review_at = datetime.now(UTC)
    await db.commit()
    return {**_vendor_row(row), "computed_score": computed}


@router.get("/breaches")
async def list_vendor_breaches(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> list[dict[str, Any]]:
    from grc_dashboard.vendor.breach_monitor import list_breach_alerts, scan_vendor_breaches

    tenant_id = get_tenant_id(request)
    await _ensure_demo_vendors(db, tenant_id)
    await scan_vendor_breaches(db, tenant_id)
    return await list_breach_alerts(db, tenant_id)


@router.post("/breaches/{alert_id}/acknowledge")
async def acknowledge_breach(
    alert_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    from grc_dashboard.db.models import VendorBreachAlert

    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(VendorBreachAlert).where(
            VendorBreachAlert.id == alert_id,
            VendorBreachAlert.tenant_id == tenant_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await db.commit()
    return {"status": "acknowledged", "id": alert_id}
