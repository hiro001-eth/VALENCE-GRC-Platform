"""Command center — SIEM metric → control → financial risk (VALENCE moat)."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Request

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import User

router = APIRouter()
_analyzer = ComplianceGapAnalyzer(FrameworkLoader())


@router.get("/posture")
async def command_center_posture(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Unified SIEM → control → ALE view for executive and sales demos."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", []) if results else []
    summary = results.get("summary", {}) if results else {}

    chains = []
    for m in metrics[:12]:
        metric_id = m.get("metric_id", "")
        related = []
        for fw in ("SOC2", "ISO27001", "NIST_CSF"):
            analysis = _analyzer.analyze_gap(fw, metrics)
            for ctrl in analysis.get("controls", []):
                if metric_id in ctrl.get("metric_ids", []):
                    related.append({
                        "framework": fw,
                        "control_id": ctrl.get("control_id"),
                        "title": ctrl.get("title", "")[:80],
                        "status": ctrl.get("status"),
                    })
        chains.append({
            "metric_id": metric_id,
            "metric_name": m.get("metric_name"),
            "value": m.get("value"),
            "rag_status": m.get("rag_status"),
            "ale_usd": m.get("ale_usd", 0),
            "var_95_usd": m.get("var_95_usd", 0),
            "controls": related[:4],
            "remediation_hint": (
                "Open remediation task and sync to ITSM"
                if m.get("rag_status") in ("Red", "Amber")
                else "Monitor — within SLA"
            ),
        })

    total_ale = summary.get("total_ale_usd") or sum(x.get("ale_usd") or 0 for x in metrics)
    red_count = sum(1 for x in metrics if x.get("rag_status") == "Red")

    return {
        "tenant_id": tenant_id,
        "headline": {
            "total_ale_usd": total_ale,
            "red_metrics": red_count,
            "overall_rag": summary.get("overall_rag", "—"),
            "data_mode": "live" if metrics else "awaiting_pipeline",
        },
        "chains": chains,
        "value_proposition": (
            "VALENCE links live SIEM telemetry to compliance controls and FAIR financial exposure — "
            "one view Vanta and Drata cannot provide natively."
        ),
    }
