"""Security Maturity Assessments — CMMI / NIST CSF maturity levels.

Drata focuses narrowly on audit readiness and does not implement true security
maturity assessments. This gives VALENCE a genuine competitive advantage for
enterprise organizations that need to demonstrate security program maturity
beyond checkbox compliance.

Features:
- CMMI 1-5 maturity scoring per security domain
- Gap analysis between current and target maturity
- Framework-specific assessment templates (NIST CSF, ISO 27001, CMMC)
- Evidence linking to maturity claims
- Trend tracking over time
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
from grc_dashboard.db.models import MaturityAssessment, User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

logger = structlog.get_logger(__name__)
router = APIRouter()

# NIST CSF Maturity Domains with descriptions
MATURITY_FRAMEWORKS: dict[str, list[dict[str, Any]]] = {
    "NIST_CSF": [
        {"domain": "Identify", "description": "Asset management, business environment, governance, risk assessment, risk management strategy"},
        {"domain": "Protect", "description": "Access control, awareness/training, data security, information protection, maintenance, protective technology"},
        {"domain": "Detect", "description": "Anomalies and events, continuous monitoring, detection processes"},
        {"domain": "Respond", "description": "Response planning, communications, analysis, mitigation, improvements"},
        {"domain": "Recover", "description": "Recovery planning, improvements, communications"},
    ],
    "ISO27001": [
        {"domain": "Information Security Policies", "description": "Management direction for information security"},
        {"domain": "Organization of Security", "description": "Internal organization and mobile devices/teleworking"},
        {"domain": "Human Resource Security", "description": "Prior to, during, and termination of employment"},
        {"domain": "Asset Management", "description": "Responsibility for assets, information classification, media handling"},
        {"domain": "Access Control", "description": "Business requirements, user access management, system and application access"},
        {"domain": "Cryptography", "description": "Cryptographic controls"},
        {"domain": "Physical Security", "description": "Secure areas and equipment"},
        {"domain": "Operations Security", "description": "Operational procedures, protection from malware, backup, logging, software control"},
        {"domain": "Communications Security", "description": "Network security management, information transfer"},
        {"domain": "Incident Management", "description": "Management of incidents and improvements"},
    ],
    "CMMC": [
        {"domain": "Access Control", "description": "Limit system access to authorized users"},
        {"domain": "Awareness & Training", "description": "Security awareness and training"},
        {"domain": "Audit & Accountability", "description": "Create, protect, and retain system audit logs"},
        {"domain": "Configuration Management", "description": "Establish and maintain baseline configurations"},
        {"domain": "Identification & Authentication", "description": "Identify and authenticate system users"},
        {"domain": "Incident Response", "description": "Establish operational incident handling capability"},
        {"domain": "Maintenance", "description": "Perform system maintenance"},
        {"domain": "Media Protection", "description": "Protect system media"},
        {"domain": "Personnel Security", "description": "Screen individuals prior to access authorization"},
        {"domain": "Physical Protection", "description": "Limit physical access"},
        {"domain": "Risk Assessment", "description": "Periodically assess risk"},
        {"domain": "Security Assessment", "description": "Periodically assess security controls"},
        {"domain": "System & Communications Protection", "description": "Monitor, control, and protect communications"},
        {"domain": "System & Information Integrity", "description": "Identify, report, and correct flaws in a timely manner"},
    ],
}

MATURITY_LEVELS = {
    1: {"name": "Initial", "description": "Ad-hoc, unpredictable, reactive"},
    2: {"name": "Managed", "description": "Project-level processes, partially planned"},
    3: {"name": "Defined", "description": "Organization-wide standards, proactive"},
    4: {"name": "Quantitatively Managed", "description": "Measured and controlled"},
    5: {"name": "Optimizing", "description": "Continuous improvement, innovation"},
}

# Demo seed data
DEMO_ASSESSMENTS = [
    ("Identify", 3, 4),
    ("Protect", 2, 4),
    ("Detect", 3, 4),
    ("Respond", 2, 3),
    ("Recover", 1, 3),
]


class AssessmentCreate(BaseModel):
    framework: str = Field(default="NIST_CSF")
    domain: str
    current_level: int = Field(ge=1, le=5)
    target_level: int = Field(ge=1, le=5)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AssessmentUpdate(BaseModel):
    current_level: int | None = Field(default=None, ge=1, le=5)
    target_level: int | None = Field(default=None, ge=1, le=5)
    findings: list[str] | None = None
    recommendations: list[str] | None = None


async def _ensure_demo_assessments(db: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await db.execute(
        select(MaturityAssessment.id).where(MaturityAssessment.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    for domain, current, target in DEMO_ASSESSMENTS:
        db.add(
            MaturityAssessment(
                id=f"MAT-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=tenant_id,
                framework="NIST_CSF",
                domain=domain,
                current_level=current,
                target_level=target,
                assessor="system",
                findings=[f"{domain} gap analysis identified areas for improvement"],
                recommendations=[f"Implement {domain.lower()} controls to reach level {target}"],
            )
        )
    await db.commit()


@router.get("/frameworks")
async def list_frameworks(current_user: User = RequireAnalyst) -> dict[str, Any]:
    """List available maturity assessment frameworks and domains."""
    return {
        "frameworks": {
            fw: {
                "domains": domains,
                "domain_count": len(domains),
            }
            for fw, domains in MATURITY_FRAMEWORKS.items()
        },
        "maturity_levels": MATURITY_LEVELS,
        "competitive_note": (
            "VALENCE supports CMMI-based maturity assessments across NIST CSF, ISO 27001, and CMMC — "
            "a capability Drata and Vanta do not offer. Enterprise organizations can demonstrate "
            "security program maturity beyond checkbox compliance."
        ),
    }


@router.get("/")
async def list_assessments(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    framework: str = "NIST_CSF",
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """List maturity assessments for the tenant."""
    tenant_id = get_tenant_id(request)
    await _ensure_demo_assessments(db, tenant_id)

    result = await db.execute(
        select(MaturityAssessment)
        .where(MaturityAssessment.tenant_id == tenant_id, MaturityAssessment.framework == framework)
        .order_by(MaturityAssessment.domain)
    )
    assessments = result.scalars().all()

    items = []
    total_current = 0
    total_target = 0
    for a in assessments:
        total_current += a.current_level
        total_target += a.target_level
        items.append({
            "id": a.id,
            "domain": a.domain,
            "current_level": a.current_level,
            "current_level_name": MATURITY_LEVELS.get(a.current_level, {}).get("name", "Unknown"),
            "target_level": a.target_level,
            "target_level_name": MATURITY_LEVELS.get(a.target_level, {}).get("name", "Unknown"),
            "gap": a.target_level - a.current_level,
            "assessor": a.assessor,
            "findings": a.findings,
            "recommendations": a.recommendations,
            "assessed_at": a.assessed_at.isoformat() if a.assessed_at else None,
        })

    avg_current = round(total_current / len(items), 1) if items else 0
    avg_target = round(total_target / len(items), 1) if items else 0

    return {
        "framework": framework,
        "tenant_id": tenant_id,
        "assessments": items,
        "summary": {
            "total_domains": len(items),
            "average_maturity": avg_current,
            "average_target": avg_target,
            "maturity_gap": round(avg_target - avg_current, 1),
            "domains_at_target": sum(1 for a in assessments if a.current_level >= a.target_level),
            "domains_below_target": sum(1 for a in assessments if a.current_level < a.target_level),
        },
        "maturity_levels": MATURITY_LEVELS,
    }


@router.post("/", status_code=201)
async def create_assessment(
    body: AssessmentCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireCISO,
) -> dict[str, Any]:
    """Create or update a maturity assessment for a domain."""
    tenant_id = get_tenant_id(request)

    # Check for existing assessment for this domain
    existing = await db.execute(
        select(MaturityAssessment).where(
            MaturityAssessment.tenant_id == tenant_id,
            MaturityAssessment.framework == body.framework,
            MaturityAssessment.domain == body.domain,
        )
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row:
        existing_row.current_level = body.current_level
        existing_row.target_level = body.target_level
        existing_row.findings = body.findings
        existing_row.recommendations = body.recommendations
        existing_row.assessor = current_user.username
        existing_row.assessed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "updated", "id": existing_row.id}

    assessment = MaturityAssessment(
        id=f"MAT-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=tenant_id,
        framework=body.framework,
        domain=body.domain,
        current_level=body.current_level,
        target_level=body.target_level,
        assessor=current_user.username,
        findings=body.findings,
        recommendations=body.recommendations,
    )
    db.add(assessment)
    await db.commit()
    return {"status": "created", "id": assessment.id}


@router.patch("/{assessment_id}")
async def update_assessment(
    assessment_id: str,
    body: AssessmentUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireCISO,
) -> dict[str, Any]:
    """Update an existing maturity assessment."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(MaturityAssessment).where(
            MaturityAssessment.id == assessment_id,
            MaturityAssessment.tenant_id == tenant_id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    if body.current_level is not None:
        assessment.current_level = body.current_level
    if body.target_level is not None:
        assessment.target_level = body.target_level
    if body.findings is not None:
        assessment.findings = body.findings
    if body.recommendations is not None:
        assessment.recommendations = body.recommendations
    assessment.assessor = current_user.username
    assessment.assessed_at = datetime.now(UTC)

    await db.commit()
    return {"status": "updated", "id": assessment_id}
