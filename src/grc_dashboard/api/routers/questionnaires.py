"""Security questionnaire auto-fill and vendor SIG-lite questionnaires."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst, RequireAuditor
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import SecurityQuestionnaireProfile, User
from grc_dashboard.db.session import get_db

router = APIRouter()
_analyzer = ComplianceGapAnalyzer(FrameworkLoader())

LIVE_METRIC_FIELDS = frozenset(
    {
        "incident_response",
        "incident_response_mttr",
        "vulnerability_management",
        "soc2_readiness",
    }
)

DEFAULT_ANSWERS = {
    "encryption_at_rest": "Yes — AES-256 for all production databases and object storage.",
    "encryption_in_transit": "Yes — TLS 1.2+ enforced for all external and internal API traffic.",
    "mfa_enforcement": "Yes — MFA required for all workforce accounts and privileged access.",
    "incident_response": "Yes — documented IR plan with defined MTTD/MTTR SLAs and tabletop exercises.",
    "vulnerability_management": "Yes — critical CVE patch SLA of 14 days; CISA KEV tracked in risk register.",
    "access_reviews": "Yes — quarterly access reviews for privileged accounts; JML process documented.",
    "data_retention": "Yes — retention schedules aligned with legal and contractual requirements.",
    "subprocessors": "Maintained list available; DPAs in place for all processors handling PII.",
    "penetration_testing": "Annual third-party penetration test; findings tracked to remediation.",
    "business_continuity": "Yes — BCP/DR tested annually with RTO/RPO defined per tier.",
}


class ProfileUpdate(BaseModel):
    company_legal_name: str = ""
    responses: dict[str, str] | None = None


def _load_sig_questions() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[4] / "rules" / "vendor_questionnaire.yaml"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh).get("questions", [])


async def _get_or_create_profile(session: AsyncSession, tenant_id: str) -> SecurityQuestionnaireProfile:
    result = await session.execute(
        select(SecurityQuestionnaireProfile).where(SecurityQuestionnaireProfile.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    row = SecurityQuestionnaireProfile(
        tenant_id=tenant_id,
        company_legal_name="",
        responses=dict(DEFAULT_ANSWERS),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/template")
async def questionnaire_template(current_user: User = RequireAuditor) -> dict[str, Any]:
    questions = _load_sig_questions()
    return {"name": "SIG Lite (VALENCE)", "version": "1.0", "questions": questions}


@router.get("/profile")
async def get_questionnaire_profile(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    profile = await _get_or_create_profile(db, tenant_id)
    responses = profile.responses or {}
    field_sources = {
        k: "live_metrics" if k in LIVE_METRIC_FIELDS else "template"
        for k in responses
    }
    return {
        "tenant_id": tenant_id,
        "company_legal_name": profile.company_legal_name,
        "responses": responses,
        "field_sources": field_sources,
        "auto_fill_version": profile.auto_fill_version,
        "approval_status": profile.approval_status,
        "approved_by": profile.approved_by,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        "purpose": "SIG Lite answers for vendor due diligence — auto-fill pulls MTTD, MTTR, CVE lag, and SOC 2 % from your live dashboard.",
    }


@router.put("/profile")
async def update_questionnaire_profile(
    body: ProfileUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    profile = await _get_or_create_profile(db, tenant_id)
    if body.company_legal_name:
        profile.company_legal_name = body.company_legal_name
    if body.responses is not None:
        merged = dict(profile.responses or {})
        merged.update(body.responses)
        profile.responses = merged
    await db.commit()
    return await get_questionnaire_profile(request, db, current_user)


@router.post("/auto-fill")
async def auto_fill_questionnaire(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Generate questionnaire answers from live metrics and compliance posture."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics = results.get("metrics", [])
    profile = await _get_or_create_profile(db, tenant_id)

    responses = dict(DEFAULT_ANSWERS)
    mttd = next((m for m in metrics if m.get("metric_id") == "KRI-MTTD-001"), None)
    mttr = next((m for m in metrics if m.get("metric_id") == "KRI-MTTR-001"), None)
    cve = next((m for m in metrics if m.get("metric_id") == "KRI-CVE-001"), None)

    if mttd:
        responses["incident_response"] = (
            f"Yes — MTTD currently {mttd.get('value')} min ({mttd.get('rag_status')} RAG). "
            "Documented IR plan with executive escalation paths."
        )
    if mttr:
        responses["incident_response_mttr"] = (
            f"MTTR: {mttr.get('value')} min. Post-incident reviews mandatory for Sev-1/2."
        )
    if cve:
        responses["vulnerability_management"] = (
            f"Critical CVE patch lag: {cve.get('value')} days ({cve.get('rag_status')}). "
            "CISA KEV catalog monitored via CERBERUS risk register."
        )

    soc2 = _analyzer.analyze_gap("SOC2", metrics)
    if soc2.get("total_controls"):
        pct = round((soc2.get("compliant", 0) / soc2["total_controls"]) * 100, 1)
        responses["soc2_readiness"] = f"SOC 2 TSC mapped controls at {pct}% compliant in continuous monitoring."

    profile.responses = responses
    profile.auto_fill_version = "metrics-v1"
    profile.approval_status = "draft"
    profile.approved_by = None
    await db.commit()

    questions = _load_sig_questions()
    filled = []
    for q in questions:
        qid = q.get("id", "")
        filled.append({
            **q,
            "answer": responses.get(qid, responses.get(q.get("maps_to", ""), "See security documentation.")),
        })

    return {
        "status": "success",
        "company_legal_name": profile.company_legal_name or tenant_id,
        "responses": responses,
        "filled_questionnaire": filled,
        "source": "metrics+compliance_posture",
    }


@router.get("/library")
async def questionnaire_library(current_user: User = RequireAuditor) -> dict[str, Any]:
    import os

    from grc_dashboard.intelligence.questionnaire_ai import QUESTIONNAIRE_LIBRARY
    return {
        "templates": [
            {"id": tid, **meta}
            for tid, meta in QUESTIONNAIRE_LIBRARY.items()
        ],
        "total_questions_available": sum(t["question_count"] for t in QUESTIONNAIRE_LIBRARY.values()),
        "ai_enabled": bool(os.getenv("OLLAMA_URL") or os.getenv("OPENAI_API_KEY")),
    }


class AiDraftRequest(BaseModel):
    template_id: str = "sig_lite"
    use_ai: bool = True


@router.post("/ai-draft")
async def ai_draft_questionnaire(
    body: AiDraftRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Vanta-scale AI questionnaire drafting — SIG, CAIQ, SOC2, ISO, NIST, HIPAA, PCI."""
    import os

    from grc_dashboard.intelligence.questionnaire_ai import (
        QUESTIONNAIRE_LIBRARY,
        draft_questionnaire_answers,
    )

    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics = results.get("metrics", []) if results else []
    profile = await _get_or_create_profile(db, tenant_id)

    mttd = next((m for m in metrics if "MTTD" in m.get("metric_id", "")), None)
    mttr = next((m for m in metrics if "MTTR" in m.get("metric_id", "")), None)
    metrics_summary = " · ".join(
        filter(None, [
            f"MTTD {mttd['value']}min" if mttd else None,
            f"MTTR {mttr['value']}min" if mttr else None,
        ])
    )
    soc2 = _analyzer.analyze_gap("SOC2", metrics)
    readiness = round((soc2.get("compliant", 0) / max(soc2.get("total_controls", 1), 1)) * 100, 1)

    tpl = QUESTIONNAIRE_LIBRARY.get(body.template_id, QUESTIONNAIRE_LIBRARY["sig_lite"])
    questions = _load_sig_questions()
    if not questions:
        questions = [{"id": k, "text": k.replace("_", " ").title()} for k in DEFAULT_ANSWERS]

    # Scale to template size with generated question stubs
    while len(questions) < min(tpl["question_count"], 30):
        idx = len(questions) + 1
        questions.append({
            "id": f"Q{idx:03d}",
            "text": f"Describe control effectiveness for security domain item {idx} per {tpl['name']}.",
        })

    context = {
        "company_name": profile.company_legal_name or tenant_id,
        "metrics_summary": metrics_summary,
        "readiness_pct": readiness,
        "llm_configured": bool(os.getenv("OLLAMA_URL") or os.getenv("OPENAI_API_KEY")),
    }
    drafted = await draft_questionnaire_answers(body.template_id, questions, context, use_ai=body.use_ai)

    merged = dict(profile.responses or {})
    merged.update(drafted["answers"])
    profile.responses = merged
    profile.auto_fill_version = f"ai-{drafted.get('sources', {}).get(list(drafted['answers'].keys())[0] if drafted['answers'] else '', 'v2')}"
    profile.approval_status = "draft"
    profile.approved_by = None
    await db.commit()

    return {
        "status": "success",
        "template": tpl,
        "drafted": drafted,
        "responses": merged,
        "message": (
            f"Drafted {drafted['total_answered']} answers "
            f"({drafted['ai_drafted_count']} via AI, rest deterministic)."
        ),
    }


@router.post("/submit-for-approval")
async def submit_questionnaire_for_approval(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    profile = await _get_or_create_profile(db, tenant_id)
    if not profile.responses:
        raise HTTPException(status_code=400, detail="Complete questionnaire before submitting")
    profile.approval_status = "pending_approval"
    profile.approved_by = None
    await db.commit()
    return {"status": "pending_approval", "message": "Questionnaire submitted for CISO review"}


@router.post("/approve")
async def approve_questionnaire(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    profile = await _get_or_create_profile(db, tenant_id)
    profile.approval_status = "approved"
    profile.approved_by = current_user.username
    await db.commit()
    return {"status": "approved", "approved_by": current_user.username}


@router.post("/reject")
async def reject_questionnaire(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    profile = await _get_or_create_profile(db, tenant_id)
    profile.approval_status = "rejected"
    profile.approved_by = current_user.username
    await db.commit()
    return {"status": "rejected", "approved_by": current_user.username}
