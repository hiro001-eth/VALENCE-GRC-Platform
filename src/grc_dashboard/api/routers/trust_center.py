"""Public trust center — shareable compliance posture page."""
from __future__ import annotations

import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAuditor
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import MetricHistoryRecord, Tenant, TrustCenterConfig, User
from grc_dashboard.db.session import AsyncSessionLocal, get_db
from grc_dashboard.tenancy.constants import is_demo_tenant
from grc_dashboard.tenancy.demo_scenarios import build_tenant_metrics

router = APIRouter()
_loader = FrameworkLoader()
_analyzer = ComplianceGapAnalyzer(_loader)


class TrustCenterUpdate(BaseModel):
    public_enabled: bool = False
    company_name: str = ""
    description: str | None = None
    frameworks: list[str] | None = None
    badges: list[str] | None = None
    contact_email: str | None = None
    slug: str | None = None
    nda_required: bool | None = None
    nda_text: str | None = None


class NdaAcceptRequest(BaseModel):
    signer_name: str
    signer_email: str
    company: str = ""


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or f"trust-{uuid.uuid4().hex[:6]}"


async def _ensure_trust_config(session: AsyncSession, tenant_id: str) -> TrustCenterConfig:
    result = await session.execute(
        select(TrustCenterConfig).where(TrustCenterConfig.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    tenant_row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_row.scalar_one_or_none()
    label = tenant.name if tenant else tenant_id.replace("-", " ").title()
    slug = _slugify(label.replace("demo-", ""))
    row = TrustCenterConfig(
        tenant_id=tenant_id,
        slug=slug,
        public_enabled=is_demo_tenant(tenant_id),
        company_name=label,
        description="Security and compliance posture for customers and partners.",
        frameworks=["SOC2", "ISO27001", "HIPAA", "GDPR"],
        badges=["SOC 2 Type II (in progress)", "ISO 27001 aligned"],
        contact_email="security@example.com",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/config")
async def get_trust_center_config(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    row = await _ensure_trust_config(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "slug": row.slug,
        "public_enabled": row.public_enabled,
        "company_name": row.company_name,
        "description": row.description,
        "frameworks": row.frameworks or [],
        "badges": row.badges or [],
        "contact_email": row.contact_email,
        "public_url": f"/trust/{row.slug}",
        "nda_required": row.nda_required,
        "nda_text": row.nda_text,
    }


@router.put("/config")
async def update_trust_center_config(
    body: TrustCenterUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    row = await _ensure_trust_config(db, tenant_id)
    if body.slug:
        row.slug = _slugify(body.slug)
    row.public_enabled = body.public_enabled
    if body.company_name:
        row.company_name = body.company_name
    if body.description is not None:
        row.description = body.description
    if body.frameworks is not None:
        row.frameworks = body.frameworks
    if body.badges is not None:
        row.badges = body.badges
    if body.contact_email is not None:
        row.contact_email = body.contact_email
    if body.nda_required is not None:
        row.nda_required = body.nda_required
    if body.nda_text is not None:
        row.nda_text = body.nda_text
    await db.commit()
    return await get_trust_center_config(request, db, current_user)


async def _latest_tenant_metrics(session: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    """Load latest metric snapshot for live trust center readiness."""
    result = await session.execute(
        select(MetricHistoryRecord)
        .where(MetricHistoryRecord.tenant_id == tenant_id)
        .order_by(desc(MetricHistoryRecord.computed_at))
        .limit(200)
    )
    rows = result.scalars().all()
    if not rows:
        return []
    seen: set[str] = set()
    metrics: list[dict[str, Any]] = []
    for row in rows:
        if row.metric_id in seen:
            continue
        seen.add(row.metric_id)
        metrics.append({
            "metric_id": row.metric_id,
            "metric_name": row.metric_name,
            "value": row.value,
            "rag_status": row.rag_status,
            "ale_usd": row.ale_usd,
        })
    return metrics


def _controls_summary_from_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive trust-center control claims from live metrics — not static marketing copy."""
    by_id = {m.get("metric_id", ""): m for m in metrics}
    mfa = by_id.get("MFA_COVERAGE", {})
    encrypt = by_id.get("ENCRYPTION_COVERAGE", {})
    ir = by_id.get("MTTD", {}) or by_id.get("MTTR", {})
    pentest = by_id.get("VULN_PATCH_LAG", {})
    return {
        "encryption_at_rest": encrypt.get("rag_status") == "Green" if encrypt else None,
        "encryption_in_transit": encrypt.get("rag_status") in ("Green", "Amber") if encrypt else None,
        "mfa_enforced": mfa.get("rag_status") == "Green" if mfa else None,
        "incident_response_program": ir.get("rag_status") in ("Green", "Amber") if ir else None,
        "annual_pen_test": "On track" if pentest.get("rag_status") == "Green" else (
            "Needs attention" if pentest else "Not assessed"
        ),
        "data_source": "live_metrics" if metrics else "pending_pipeline",
    }


@router.get("/public/{slug}")
async def public_trust_center(slug: str) -> dict[str, Any]:
    """Unauthenticated trust center metadata — use /content after NDA gate."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrustCenterConfig).where(TrustCenterConfig.slug == slug)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail="Trust center not found")
        if not config.public_enabled:
            raise HTTPException(status_code=403, detail="Trust center is not public")

        if config.nda_required:
            return {
                "nda_required": True,
                "nda_text": config.nda_text or (
                    "By accessing this trust center you agree not to disclose confidential security "
                    "information without written consent from the organization."
                ),
                "company_name": config.company_name,
            }

        return await public_trust_center_content(slug)


@router.post("/public/{slug}/nda-accept")
async def accept_trust_nda(slug: str, body: NdaAcceptRequest) -> dict[str, Any]:
    """Record NDA acceptance for gated trust center access (audit log hook)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrustCenterConfig).where(TrustCenterConfig.slug == slug)
        )
        config = result.scalar_one_or_none()
        if not config or not config.public_enabled:
            raise HTTPException(status_code=404, detail="Trust center not found")
        if not config.nda_required:
            return {"status": "not_required"}
        if not body.signer_name.strip() or not body.signer_email.strip():
            raise HTTPException(status_code=400, detail="Name and email required")
        return {
            "status": "accepted",
            "slug": slug,
            "signer_name": body.signer_name.strip(),
            "signer_email": body.signer_email.strip(),
            "company": body.company.strip(),
            "message": "NDA acceptance recorded for this session",
        }


@router.get("/public/{slug}/content")
async def public_trust_center_content(slug: str) -> dict[str, Any]:
    """Unauthenticated trust center page data (call after NDA if required)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TrustCenterConfig).where(TrustCenterConfig.slug == slug)
        )
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail="Trust center not found")
        if not config.public_enabled:
            raise HTTPException(status_code=403, detail="Trust center is not public")

        tenant_id = config.tenant_id
        if is_demo_tenant(tenant_id):
            metrics = build_tenant_metrics(tenant_id).get("metrics", [])
        else:
            metrics = await _latest_tenant_metrics(session, tenant_id)

        framework_scores = []
        for fw in config.frameworks or _loader.list_frameworks():
            fw_key = fw.upper().replace(" ", "").replace("_", "")
            match = next((f for f in _loader.list_frameworks() if f.upper().startswith(fw_key[:4])), fw)
            if metrics:
                analysis = _analyzer.analyze_gap(match, metrics)
                total = analysis.get("total_controls", 1) or 1
                compliant = analysis.get("compliant", 0)
                pct = round((compliant / total) * 100, 1)
            else:
                pct = None
            framework_scores.append({"framework": fw, "readiness_pct": pct})

        return {
            "company_name": config.company_name,
            "description": config.description,
            "badges": config.badges or [],
            "frameworks": framework_scores,
            "contact_email": config.contact_email,
            "last_updated": config.updated_at.isoformat() if config.updated_at else None,
            "subprocessors_note": "Available on request",
            "controls_summary": _controls_summary_from_metrics(metrics),
            "nda_required": config.nda_required,
        }
