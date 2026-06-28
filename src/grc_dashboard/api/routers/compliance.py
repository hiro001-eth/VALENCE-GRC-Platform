"""Compliance router: framework coverage, gap analysis using dynamic YAML config rules."""
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAuditor
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import User
from grc_dashboard.db.persistence import enrich_controls_with_evidence, list_evidence
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()

loader = FrameworkLoader()
analyzer = ComplianceGapAnalyzer(loader)


@router.get("/frameworks")
async def list_frameworks() -> list[str]:
    """List names of all loaded compliance frameworks."""
    return loader.list_frameworks()


@router.get("/summary")
async def get_compliance_summary(
    request: Request,
    current_user: User = RequireAuditor,
) -> list[dict[str, Any]]:
    """Return high-level coverage percentage for all compliance frameworks."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    summary = []
    frameworks = loader.list_frameworks()
    for fw in frameworks:
        analysis = analyzer.analyze_gap(fw, metrics)
        summary.append({
            "framework": fw,
            "full_name": analysis.get("full_name", fw),
            "coverage_pct": analysis.get("coverage_pct", 0.0),
            "readiness_pct": analysis.get("readiness_pct", 0.0),
        })
    return summary


@router.get("/readiness")
async def get_readiness_overview(
    request: Request,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Weighted compliance readiness across DORA, NIS2, and SOC 2."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    return analyzer.aggregate_readiness(metrics)


@router.get("/cross-framework")
async def get_cross_framework_map(
    request: Request,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Unified control view mapped across SOC2, ISO, HIPAA, GDPR, NIST."""
    from grc_dashboard.compliance.cross_framework import build_cross_framework_view

    results = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    gap_results = {fw: analyzer.analyze_gap(fw, metrics) for fw in loader.list_frameworks()}
    unified = build_cross_framework_view(gap_results)
    compliant = sum(1 for u in unified if u["overall_status"] == "Compliant")
    return {
        "unified_controls": unified,
        "total_unified": len(unified),
        "compliant_unified": compliant,
        "coverage_pct": round((compliant / len(unified)) * 100, 1) if unified else 0,
    }


@router.get("/{framework}/evidence-map")
async def get_control_evidence_map(
    framework: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Map each control to linked evidence vault records."""
    fw_upper = framework.upper()
    frameworks = loader.list_frameworks()
    if fw_upper not in frameworks:
        raise HTTPException(
            status_code=404,
            detail=f"Compliance framework '{framework}' not found. Available: {frameworks}",
        )

    tenant_id = get_tenant_id(request)
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    analysis = analyzer.analyze_gap(fw_upper, metrics)
    controls = await enrich_controls_with_evidence(
        db, tenant_id, analysis.get("controls", [])
    )
    return {
        "framework": fw_upper,
        "full_name": analysis.get("full_name", fw_upper),
        "controls": controls,
    }


@router.get("/{framework}")
async def get_framework_coverage(
    framework: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Return detailed control-level compliance status and gap analysis logs."""
    fw_upper = framework.upper()
    frameworks = loader.list_frameworks()
    if fw_upper not in frameworks:
        raise HTTPException(
            status_code=404,
            detail=f"Compliance framework '{framework}' not found. Available: {frameworks}",
        )

    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    analysis = analyzer.analyze_gap(fw_upper, metrics)
    analysis["controls"] = await enrich_controls_with_evidence(
        db, get_tenant_id(request), analysis.get("controls", [])
    )
    return analysis
