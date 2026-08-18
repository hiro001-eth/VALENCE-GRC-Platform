"""Risk Treatment Plans — Accept/Mitigate/Transfer/Avoid workflows.

Vanta's risk register is basic — it tracks risks but does not support
quantitative risk analysis, FAIR-based scoring, or sophisticated risk
treatment workflows. VALENCE beats them on risk depth.

Features:
- Four treatment strategies: Accept, Mitigate, Transfer, Avoid
- CISO-level approval workflows
- Investment vs risk reduction ROI tracking
- Residual risk scoring post-treatment
- Evidence linking to treatment completion
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAnalyst, RequireCISO
from grc_dashboard.db.models import RiskTreatmentPlan, User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

logger = structlog.get_logger(__name__)
router = APIRouter()

# Demo seed
DEMO_TREATMENTS = [
    {
        "risk_id": "RISK-CVE-001",
        "treatment_type": "mitigate",
        "description": "Implement automated patch management pipeline to reduce CVE exposure window from 14 days to < 3 days.",
        "owner": "analyst",
        "status": "in_progress",
        "investment_usd": 45000,
        "expected_risk_reduction_pct": 65.0,
        "residual_risk_score": 35.0,
    },
    {
        "risk_id": "RISK-DLP-001",
        "treatment_type": "mitigate",
        "description": "Deploy DLP endpoint agents and configure cloud egress monitoring rules.",
        "owner": "ciso",
        "status": "approved",
        "investment_usd": 120000,
        "expected_risk_reduction_pct": 80.0,
        "residual_risk_score": 20.0,
    },
    {
        "risk_id": "RISK-3P-001",
        "treatment_type": "transfer",
        "description": "Transfer third-party breach exposure via cyber insurance policy with $5M aggregate coverage.",
        "owner": "ciso",
        "status": "completed",
        "investment_usd": 35000,
        "expected_risk_reduction_pct": 70.0,
        "residual_risk_score": 30.0,
    },
    {
        "risk_id": "RISK-LEGACY-001",
        "treatment_type": "accept",
        "description": "Accept residual risk from legacy system (EOL Q3 2026). Risk accepted by CISO with board acknowledgment.",
        "owner": "ciso",
        "status": "completed",
        "investment_usd": 0,
        "expected_risk_reduction_pct": 0.0,
        "residual_risk_score": 85.0,
    },
]


class TreatmentCreate(BaseModel):
    risk_id: str
    treatment_type: str = Field(pattern="^(accept|mitigate|transfer|avoid)$")
    description: str | None = None
    owner: str = ""
    investment_usd: float | None = None
    expected_risk_reduction_pct: float | None = Field(default=None, ge=0, le=100)
    due_date: str | None = None


class TreatmentUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(draft|approved|in_progress|completed)$")
    description: str | None = None
    investment_usd: float | None = None
    expected_risk_reduction_pct: float | None = Field(default=None, ge=0, le=100)
    residual_risk_score: float | None = Field(default=None, ge=0, le=100)


async def _ensure_demo_treatments(db: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await db.execute(
        select(RiskTreatmentPlan.id).where(RiskTreatmentPlan.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    for t in DEMO_TREATMENTS:
        db.add(
            RiskTreatmentPlan(
                id=f"RTP-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=tenant_id,
                **t,
            )
        )
    await db.commit()


@router.get("/")
async def list_treatments(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """List all risk treatment plans for the tenant."""
    tenant_id = get_tenant_id(request)
    await _ensure_demo_treatments(db, tenant_id)

    result = await db.execute(
        select(RiskTreatmentPlan)
        .where(RiskTreatmentPlan.tenant_id == tenant_id)
        .order_by(RiskTreatmentPlan.created_at.desc())
    )
    plans = result.scalars().all()

    items = []
    total_investment = 0.0
    for p in plans:
        total_investment += p.investment_usd or 0
        items.append({
            "id": p.id,
            "risk_id": p.risk_id,
            "treatment_type": p.treatment_type,
            "description": p.description,
            "owner": p.owner,
            "status": p.status,
            "residual_risk_score": p.residual_risk_score,
            "investment_usd": p.investment_usd,
            "expected_risk_reduction_pct": p.expected_risk_reduction_pct,
            "approved_by": p.approved_by,
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
            "due_date": p.due_date.isoformat() if p.due_date else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    by_type = {}
    for p in plans:
        by_type[p.treatment_type] = by_type.get(p.treatment_type, 0) + 1

    by_status = {}
    for p in plans:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    return {
        "plans": items,
        "summary": {
            "total_plans": len(items),
            "total_investment_usd": total_investment,
            "by_treatment_type": by_type,
            "by_status": by_status,
            "average_risk_reduction_pct": round(
                sum(p.expected_risk_reduction_pct or 0 for p in plans) / max(len(plans), 1), 1
            ),
        },
        "treatment_types": {
            "accept": "Acknowledge the risk without action (documented CISO decision)",
            "mitigate": "Implement controls to reduce the risk to an acceptable level",
            "transfer": "Transfer risk via insurance, outsourcing, or contractual obligation",
            "avoid": "Eliminate the risk by removing the threat source or asset",
        },
    }


@router.post("/", status_code=201)
async def create_treatment(
    body: TreatmentCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireCISO,
) -> dict[str, Any]:
    """Create a risk treatment plan."""
    tenant_id = get_tenant_id(request)
    due = None
    if body.due_date:
        due = datetime.fromisoformat(body.due_date.replace("Z", "+00:00"))

    plan = RiskTreatmentPlan(
        id=f"RTP-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=tenant_id,
        risk_id=body.risk_id,
        treatment_type=body.treatment_type,
        description=body.description,
        owner=body.owner or current_user.username,
        investment_usd=body.investment_usd,
        expected_risk_reduction_pct=body.expected_risk_reduction_pct,
        due_date=due,
    )
    db.add(plan)
    await db.commit()
    return {"status": "created", "id": plan.id}


@router.patch("/{plan_id}")
async def update_treatment(
    plan_id: str,
    body: TreatmentUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireCISO,
) -> dict[str, Any]:
    """Update a risk treatment plan status or details."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(RiskTreatmentPlan).where(
            RiskTreatmentPlan.id == plan_id,
            RiskTreatmentPlan.tenant_id == tenant_id,
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Treatment plan not found")

    if body.status is not None:
        if body.status == "approved" and plan.status == "draft":
            plan.approved_by = current_user.username
            plan.approved_at = datetime.now(UTC)
        plan.status = body.status
    if body.description is not None:
        plan.description = body.description
    if body.investment_usd is not None:
        plan.investment_usd = body.investment_usd
    if body.expected_risk_reduction_pct is not None:
        plan.expected_risk_reduction_pct = body.expected_risk_reduction_pct
    if body.residual_risk_score is not None:
        plan.residual_risk_score = body.residual_risk_score

    await db.commit()
    return {"status": "updated", "id": plan_id}
