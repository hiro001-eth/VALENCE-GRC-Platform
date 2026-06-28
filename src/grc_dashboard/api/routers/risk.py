"""Risk router: Monte Carlo simulations, VaR heatmap."""
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import RiskRegisterEntry, User
from grc_dashboard.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/monte-carlo")
async def get_monte_carlo(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Return Monte Carlo simulation results for all metrics."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    mc_results = []
    for m in metrics:
        mc_results.append({
            "metric_id": m.get("metric_id"),
            "metric_name": m.get("metric_name"),
            "rag_status": m.get("rag_status"),
            "average_exposure_usd": m.get("ale_usd", 0),
            "var_95_usd": m.get("var_95_usd", 0),
            "probability_of_breach": m.get("probability_of_breach", 0),
            "breach_threshold_usd": 1_000_000,
        })

    total_ale = sum(m.get("ale_usd", 0) for m in metrics)
    total_var = sum(m.get("var_95_usd", 0) for m in metrics)

    return {
        "run_id": results.get("run_id", ""),
        "simulations_per_metric": 1000,
        "breach_threshold_usd": 1_000_000,
        "portfolio_summary": {
            "total_expected_loss_usd": total_ale,
            "portfolio_var_95_usd": total_var,
            "highest_risk_metric": max(metrics, key=lambda x: x.get("var_95_usd", 0), default={}).get("metric_id", "N/A"),
        },
        "metrics": mc_results,
    }


@router.get("/heatmap")
async def get_risk_heatmap(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Return 5×5 risk heatmap data (Likelihood × Impact)."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    def _rag_to_coords(m: dict[str, Any]) -> dict[str, Any]:
        prob = m.get("probability_of_breach", 0.1)
        ale = m.get("ale_usd", 0)
        # Map to 1-5 scale
        likelihood = max(1, min(5, int(prob * 5) + 1))
        impact = 1
        if ale < 50_000:       impact = 1
        elif ale < 200_000:    impact = 2
        elif ale < 500_000:    impact = 3
        elif ale < 1_000_000:  impact = 4
        else:                  impact = 5
        return {
            "metric_id": m.get("metric_id"),
            "metric_name": m.get("metric_name"),
            "likelihood": likelihood,
            "impact": impact,
            "risk_score": likelihood * impact,
            "rag_status": m.get("rag_status"),
        }

    heatmap_data = [_rag_to_coords(m) for m in metrics]
    return {"metrics": heatmap_data, "max_score": 25}


@router.get("/var")
async def get_var_summary(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Return Value-at-Risk summary for board reporting."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    sorted_by_var = sorted(metrics, key=lambda x: x.get("var_95_usd", 0), reverse=True)

    return {
        "currency": "USD",
        "confidence_level": "95th percentile",
        "top_risks": [
            {
                "rank": i + 1,
                "metric_id": m.get("metric_id"),
                "metric_name": m.get("metric_name"),
                "var_95_usd": m.get("var_95_usd", 0),
                "probability_of_breach": m.get("probability_of_breach", 0),
            }
            for i, m in enumerate(sorted_by_var[:5])
        ],
        "total_portfolio_var_95": sum(m.get("var_95_usd", 0) for m in metrics),
    }


@router.get("/register")
async def get_risk_register(
    request: Request,
    current_user: User = RequireAnalyst,
) -> list[dict[str, Any]]:
    """CERBERUS risk register — CVE-driven open risks."""
    tenant_id = get_tenant_id(request)
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(RiskRegisterEntry)
            .where(RiskRegisterEntry.tenant_id == tenant_id)
            .order_by(RiskRegisterEntry.created_at.desc())
        )
        return [
            {
                "id": r.id,
                "cve_id": r.cve_id,
                "title": r.title,
                "severity": r.severity,
                "owner": r.owner,
                "status": r.status,
                "source": r.source,
                "metric_id": r.metric_id,
                "finding_id": r.finding_id,
                "notes": r.notes,
                "created_at": r.created_at.isoformat(),
            }
            for r in result.scalars().all()
        ]
