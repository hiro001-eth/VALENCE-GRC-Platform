"""What-If Risk Budget Simulator — No competitor has this.

Allows CISOs to simulate budget allocation changes and instantly see
how the risk profile (VaR, ALE, compliance coverage) shifts.
"""
import math
import random
from typing import Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from grc_dashboard.api.tenant_context import get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import User

logger = structlog.get_logger(__name__)
router = APIRouter()


class WhatIfScenario(BaseModel):
    """A single what-if scenario adjustment."""
    metric_id: str
    adjustment_pct: float  # e.g. -30 means "reduce value by 30%"
    investment_usd: float = 0  # optional: budget spent to achieve this


class WhatIfRequest(BaseModel):
    """Request body for what-if simulation."""
    scenarios: list[WhatIfScenario]
    simulation_runs: int = 1000


# Investment-to-improvement mapping (how much $ buys what % improvement)
INVESTMENT_MODELS = {
    "KRI-MTTD-001": {"cost_per_pct": 15000, "label": "Detection tooling / SIEM rules", "max_improvement": 80},
    "KRI-MTTR-001": {"cost_per_pct": 20000, "label": "SOC analyst staffing / SOAR playbooks", "max_improvement": 70},
    "KPI-FPR-001":  {"cost_per_pct": 8000,  "label": "ML model tuning / rule refinement", "max_improvement": 60},
    "KRI-CVE-001":  {"cost_per_pct": 12000, "label": "Patch automation / vulnerability scanner", "max_improvement": 90},
    "KPI-PHI-001":  {"cost_per_pct": 5000,  "label": "PAM license expansion / access reviews", "max_improvement": 30},
    "KRI-DLP-001":  {"cost_per_pct": 10000, "label": "DLP agent deployment / policy tuning", "max_improvement": 75},
}

# RAG thresholds per metric — aligned with rules/threshold_config.yaml
RAG_THRESHOLDS = {
    "KRI-MTTD-001": {"green_max": 2, "amber_max": 4, "unit": "hours", "lower_is_better": True},
    "KRI-MTTR-001": {"green_max": 24, "amber_max": 48, "unit": "hours", "lower_is_better": True},
    "KPI-FPR-001":  {"green_max": 25, "amber_max": 40, "unit": "%", "lower_is_better": True},
    "KRI-CVE-001":  {"green_max": 3, "amber_max": 7, "unit": "days", "lower_is_better": True},
    "KPI-PHI-001":  {"green_max": 100, "amber_max": 90, "unit": "%", "lower_is_better": False},
    "KRI-DLP-001":  {"green_max": 15, "amber_max": 50, "unit": "incidents", "lower_is_better": True},
}


def _classify_rag(metric_id: str, value: float) -> str:
    """Classify a metric value into RAG status."""
    t = RAG_THRESHOLDS.get(metric_id)
    if not t:
        return "Amber"
    if t["lower_is_better"]:
        if value <= t["green_max"]:
            return "Green"
        elif value <= t["amber_max"]:
            return "Amber"
        return "Red"
    else:
        if value >= t["green_max"]:
            return "Green"
        elif value >= t["amber_max"]:
            return "Amber"
        return "Red"


def _monte_carlo_var(value: float, metric_id: str, runs: int = 1000) -> dict[str, float]:
    """Run a mini Monte Carlo simulation for a single adjusted metric."""
    t = RAG_THRESHOLDS.get(metric_id, {})
    base_ale = value * 10000 if t.get("lower_is_better", True) else (100 - value) * 10000
    losses = []
    for _ in range(runs):
        freq = random.expovariate(1.0 / max(0.5, value / 10))
        magnitude = random.lognormvariate(math.log(base_ale + 1), 0.8)
        losses.append(freq * magnitude)
    losses.sort()
    return {
        "ale_usd": round(sum(losses) / len(losses)),
        "var_95_usd": round(losses[int(len(losses) * 0.95)]),
        "probability_of_breach": round(min(1.0, len([l for l in losses if l > 500000]) / len(losses)), 3),
        "curve": [round(l) for l in losses],
    }


@router.post("/simulate")
async def simulate_whatif(
    request: Request,
    body: WhatIfRequest,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Simulate what-if scenarios and return projected risk profile changes."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    if not metrics:
        return {"error": "No metrics loaded yet. Run a pipeline first."}

    # Build current state
    current_state = {m["metric_id"]: dict(m) for m in metrics}
    projected_metrics = []
    total_investment = 0
    changes = []

    for scenario in body.scenarios:
        mid = scenario.metric_id
        if mid not in current_state:
            continue

        original = current_state[mid]
        original_value = original.get("value", 0)

        # Apply adjustment
        adjustment = scenario.adjustment_pct / 100.0
        t = RAG_THRESHOLDS.get(mid, {})
        if t.get("lower_is_better", True):
            new_value = max(0, original_value * (1 + adjustment))  # negative adjustment = improvement
        else:
            new_value = min(100, original_value * (1 - adjustment))  # negative adjustment = improvement

        # Calculate new RAG and risk
        new_rag = _classify_rag(mid, new_value)
        mc = _monte_carlo_var(new_value, mid, body.simulation_runs)

        projected = {
            **original,
            "value": round(new_value, 2),
            "rag_status": new_rag,
            "ale_usd": mc["ale_usd"],
            "var_95_usd": mc["var_95_usd"],
            "probability_of_breach": mc["probability_of_breach"],
            "curve": mc["curve"],
            "is_modified": True,
        }
        projected_metrics.append(projected)
        total_investment += scenario.investment_usd

        changes.append({
            "metric_id": mid,
            "metric_name": original.get("metric_name", mid),
            "original_value": original_value,
            "projected_value": round(new_value, 2),
            "original_rag": original.get("rag_status", "NoData"),
            "projected_rag": new_rag,
            "original_var_usd": original.get("var_95_usd", 0),
            "projected_var_usd": mc["var_95_usd"],
            "var_delta_usd": original.get("var_95_usd", 0) - mc["var_95_usd"],
            "original_ale_usd": original.get("ale_usd", 0),
            "projected_ale_usd": mc["ale_usd"],
            "ale_delta_usd": original.get("ale_usd", 0) - mc["ale_usd"],
            "investment_usd": scenario.investment_usd,
        })

    # Add unmodified metrics
    modified_ids = {s.metric_id for s in body.scenarios}
    for m in metrics:
        if m["metric_id"] not in modified_ids:
            mc_orig = _monte_carlo_var(m.get("value", 0), m["metric_id"], body.simulation_runs)
            projected_metrics.append({**m, "curve": mc_orig["curve"], "is_modified": False})

    original_total_var = sum(m.get("var_95_usd", 0) for m in metrics)
    original_total_ale = sum(m.get("ale_usd", 0) for m in metrics)
    projected_total_var = sum(m.get("var_95_usd", 0) for m in projected_metrics)
    projected_total_ale = sum(m.get("ale_usd", 0) for m in projected_metrics)

    roi = (original_total_var - projected_total_var) / max(1, total_investment) if total_investment > 0 else 0

    # Build portfolio curves
    orig_portfolio_curve = [0] * body.simulation_runs
    proj_portfolio_curve = [0] * body.simulation_runs
    
    for m in metrics:
        mc_o = _monte_carlo_var(m.get("value", 0), m["metric_id"], body.simulation_runs)
        for i in range(body.simulation_runs):
            orig_portfolio_curve[i] += mc_o["curve"][i]
            
    for m in projected_metrics:
        for i in range(body.simulation_runs):
            proj_portfolio_curve[i] += m.get("curve", [0]*body.simulation_runs)[i]

    # Clean up curve data from individual metrics before returning to avoid massive payload size
    for m in projected_metrics:
        m.pop("curve", None)

    return {
        "simulation": {
            "runs": body.simulation_runs,
            "scenarios_applied": len(changes),
            "total_investment_usd": total_investment,
            "original_loss_curve": orig_portfolio_curve,
            "projected_loss_curve": proj_portfolio_curve,
        },
        "current_portfolio": {
            "total_var_95_usd": original_total_var,
            "total_ale_usd": original_total_ale,
            "red_count": sum(1 for m in metrics if m.get("rag_status") == "Red"),
            "amber_count": sum(1 for m in metrics if m.get("rag_status") == "Amber"),
            "green_count": sum(1 for m in metrics if m.get("rag_status") == "Green"),
        },
        "projected_portfolio": {
            "total_var_95_usd": projected_total_var,
            "total_ale_usd": projected_total_ale,
            "var_reduction_usd": original_total_var - projected_total_var,
            "ale_reduction_usd": original_total_ale - projected_total_ale,
            "roi_ratio": round(roi, 2),
            "red_count": sum(1 for m in projected_metrics if m.get("rag_status") == "Red"),
            "amber_count": sum(1 for m in projected_metrics if m.get("rag_status") == "Amber"),
            "green_count": sum(1 for m in projected_metrics if m.get("rag_status") == "Green"),
        },
        "changes": changes,
        "projected_metrics": projected_metrics,
    }


@router.get("/presets")
async def get_whatif_presets(
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Return pre-built what-if scenarios that CISOs commonly evaluate."""
    return {
        "presets": [
            {
                "id": "hire_soc_analysts",
                "name": "Hire 2 SOC Analysts",
                "description": "Adding 2 FTE SOC analysts typically reduces MTTR by 30% and MTTD by 15%",
                "estimated_annual_cost_usd": 240000,
                "scenarios": [
                    {"metric_id": "KRI-MTTR-001", "adjustment_pct": -30, "investment_usd": 160000},
                    {"metric_id": "KRI-MTTD-001", "adjustment_pct": -15, "investment_usd": 80000},
                ],
            },
            {
                "id": "deploy_soar",
                "name": "Deploy SOAR Platform",
                "description": "Automated playbooks reduce MTTR by 50% and FPR by 25%",
                "estimated_annual_cost_usd": 180000,
                "scenarios": [
                    {"metric_id": "KRI-MTTR-001", "adjustment_pct": -50, "investment_usd": 120000},
                    {"metric_id": "KPI-FPR-001", "adjustment_pct": -25, "investment_usd": 60000},
                ],
            },
            {
                "id": "patch_automation",
                "name": "Automated Patch Management",
                "description": "Reduces CVE patch lag by 75% through automated deployment pipelines",
                "estimated_annual_cost_usd": 95000,
                "scenarios": [
                    {"metric_id": "KRI-CVE-001", "adjustment_pct": -75, "investment_usd": 95000},
                ],
            },
            {
                "id": "ml_detection",
                "name": "ML-Enhanced Detection",
                "description": "ML models improve detection accuracy, reducing MTTD by 40% and FPR by 45%",
                "estimated_annual_cost_usd": 320000,
                "scenarios": [
                    {"metric_id": "KRI-MTTD-001", "adjustment_pct": -40, "investment_usd": 200000},
                    {"metric_id": "KPI-FPR-001", "adjustment_pct": -45, "investment_usd": 120000},
                ],
            },
            {
                "id": "full_dlp",
                "name": "Enterprise DLP Expansion",
                "description": "Full endpoint + cloud DLP coverage reduces violations by 60%",
                "estimated_annual_cost_usd": 150000,
                "scenarios": [
                    {"metric_id": "KRI-DLP-001", "adjustment_pct": -60, "investment_usd": 150000},
                ],
            },
        ],
        "investment_models": INVESTMENT_MODELS,
    }
