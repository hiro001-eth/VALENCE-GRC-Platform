"""Breach Cost Simulation — FAIR-based incident cost modeling.

No competitor offers Monte Carlo breach cost simulation with FAIR taxonomy.
This gives CISOs quantifiable dollar impact for board-level risk discussions.

Features:
- FAIR-based cost component modeling (productivity, response, fines, reputation)
- Monte Carlo simulation with configurable iterations
- Regulatory fine estimation (GDPR, HIPAA, PCI DSS)
- Per-record cost modeling based on Ponemon/IBM data
- Historical scenario comparison
"""
from __future__ import annotations

import math
import random
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireCISO
from grc_dashboard.db.models import BreachSimulation, User
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()

# IBM/Ponemon average breach cost components (2024 data)
COST_PER_RECORD_USD = {
    "healthcare": 10.93,
    "financial": 5.90,
    "technology": 4.97,
    "energy": 4.72,
    "pharma": 4.82,
    "education": 3.65,
    "default": 4.45,
}

REGULATORY_FINE_MODELS = {
    "GDPR": {"max_pct_revenue": 0.04, "per_record": 150, "max_fine_eur": 20_000_000},
    "HIPAA": {"per_violation": 50000, "annual_cap": 1_500_000, "willful_multiplier": 3},
    "PCI_DSS": {"per_month_noncompliant": 100000, "per_record": 50, "max_fine": 500_000},
    "SOX": {"per_violation": 5_000_000, "imprisonment_years": 20},
}


class SimulationRequest(BaseModel):
    scenario_name: str
    threat_actor: str = Field(default="external", pattern="^(external|insider|nation_state|hacktivism)$")
    attack_vector: str = Field(default="phishing", pattern="^(phishing|ransomware|supply_chain|insider_threat|zero_day|credential_stuffing|web_app)$")
    records_exposed: int = Field(ge=100, le=100_000_000, default=50000)
    industry: str = "technology"
    annual_revenue_usd: float = Field(default=50_000_000, ge=0)
    regulations: list[str] = Field(default_factory=lambda: ["GDPR", "SOC2"])
    monte_carlo_iterations: int = Field(default=10000, ge=1000, le=100000)
    detection_days: int = Field(default=197, ge=1, le=365)
    containment_days: int = Field(default=69, ge=1, le=365)


def _run_monte_carlo(params: SimulationRequest) -> dict[str, Any]:
    """Execute FAIR-based Monte Carlo breach cost simulation."""
    base_cost = COST_PER_RECORD_USD.get(params.industry, COST_PER_RECORD_USD["default"])
    results = []

    for _ in range(params.monte_carlo_iterations):
        # Stochastic per-record cost (lognormal distribution)
        record_cost = random.lognormvariate(math.log(base_cost), 0.3)
        records = int(params.records_exposed * random.uniform(0.5, 1.5))

        # FAIR cost components
        productivity_loss = records * record_cost * 0.15 * random.uniform(0.8, 1.4)
        response_cost = records * record_cost * 0.30 * random.uniform(0.7, 1.5)
        notification_cost = records * 2.5 * random.uniform(0.8, 1.2)  # avg $2.50/notification
        reputation_damage = params.annual_revenue_usd * random.uniform(0.01, 0.05)
        forensics = random.uniform(100000, 500000) * (1.5 if params.threat_actor == "nation_state" else 1.0)
        legal_cost = records * random.uniform(1.0, 5.0)

        # Regulatory fines
        reg_fines = 0.0
        for reg in params.regulations:
            model = REGULATORY_FINE_MODELS.get(reg, {})
            if reg == "GDPR":
                gdpr_fine = min(
                    records * model.get("per_record", 150) * random.uniform(0.1, 0.5),
                    params.annual_revenue_usd * model.get("max_pct_revenue", 0.04),
                    model.get("max_fine_eur", 20_000_000) * 1.1,  # EUR->USD
                )
                reg_fines += gdpr_fine
            elif reg == "HIPAA":
                hipaa_fine = min(
                    records * model.get("per_violation", 50000) * random.uniform(0.001, 0.01),
                    model.get("annual_cap", 1_500_000),
                )
                reg_fines += hipaa_fine
            elif reg == "PCI_DSS":
                pci_fine = min(
                    records * model.get("per_record", 50) * random.uniform(0.1, 0.3),
                    model.get("max_fine", 500_000),
                )
                reg_fines += pci_fine

        # Detection/containment time multiplier
        time_multiplier = 1.0 + (params.detection_days / 365.0) * 0.3

        total = (productivity_loss + response_cost + notification_cost +
                 reputation_damage + forensics + legal_cost + reg_fines) * time_multiplier
        results.append({
            "total": round(total, 2),
            "productivity_loss": round(productivity_loss, 2),
            "response_cost": round(response_cost, 2),
            "notification_cost": round(notification_cost, 2),
            "reputation_damage": round(reputation_damage, 2),
            "forensics": round(forensics, 2),
            "legal_cost": round(legal_cost, 2),
            "regulatory_fines": round(reg_fines, 2),
        })

    totals = sorted([r["total"] for r in results])
    n = len(totals)

    return {
        "iterations": params.monte_carlo_iterations,
        "mean_cost_usd": round(sum(totals) / n, 2),
        "median_cost_usd": round(totals[n // 2], 2),
        "p5_cost_usd": round(totals[int(n * 0.05)], 2),
        "p95_cost_usd": round(totals[int(n * 0.95)], 2),
        "p99_cost_usd": round(totals[int(n * 0.99)], 2),
        "min_cost_usd": round(totals[0], 2),
        "max_cost_usd": round(totals[-1], 2),
        "std_dev_usd": round((sum((t - sum(totals)/n)**2 for t in totals) / n) ** 0.5, 2),
        "cost_breakdown_mean": {
            k: round(sum(r[k] for r in results) / n, 2)
            for k in ["productivity_loss", "response_cost", "notification_cost",
                       "reputation_damage", "forensics", "legal_cost", "regulatory_fines"]
        },
        "loss_exceedance_curve": [
            {"threshold_usd": round(totals[int(n * pct)], 2), "exceedance_pct": round((1 - pct) * 100, 1)}
            for pct in [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
        ],
    }


@router.post("/simulate")
async def simulate_breach(
    body: SimulationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireCISO,
) -> dict[str, Any]:
    """Run FAIR-based Monte Carlo breach cost simulation."""
    tenant_id = get_tenant_id(request)
    sim_results = _run_monte_carlo(body)

    # Persist simulation
    sim_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
    db.add(
        BreachSimulation(
            id=sim_id,
            tenant_id=tenant_id,
            scenario_name=body.scenario_name,
            threat_actor=body.threat_actor,
            attack_vector=body.attack_vector,
            records_exposed=body.records_exposed,
            estimated_cost_usd=sim_results["mean_cost_usd"],
            simulation_params=body.model_dump(),
            results=sim_results,
            created_by=current_user.username,
        )
    )
    await db.commit()

    return {
        "simulation_id": sim_id,
        "scenario": body.scenario_name,
        "params": body.model_dump(),
        "results": sim_results,
        "competitive_note": (
            "FAIR-based breach cost simulation with Monte Carlo analysis — "
            "a capability no competitor (Vanta, Drata, Sprinto) offers natively."
        ),
    }


@router.get("/history")
async def simulation_history(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireCISO,
) -> list[dict[str, Any]]:
    """List previous breach simulations."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(BreachSimulation)
        .where(BreachSimulation.tenant_id == tenant_id)
        .order_by(BreachSimulation.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": s.id,
            "scenario_name": s.scenario_name,
            "threat_actor": s.threat_actor,
            "attack_vector": s.attack_vector,
            "records_exposed": s.records_exposed,
            "estimated_cost_usd": s.estimated_cost_usd,
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in result.scalars().all()
    ]


@router.get("/benchmarks")
async def industry_benchmarks(
    current_user: User = RequireCISO,
) -> dict[str, Any]:
    """Return industry breach cost benchmarks from IBM/Ponemon data."""
    return {
        "source": "IBM/Ponemon Cost of a Data Breach Report 2024",
        "global_average_usd": 4_880_000,
        "by_industry": {
            industry: {
                "per_record_usd": cost,
                "avg_breach_size_records": 25575,
                "estimated_total_usd": round(cost * 25575, 2),
            }
            for industry, cost in COST_PER_RECORD_USD.items()
        },
        "cost_factors": {
            "mean_detection_days": 197,
            "mean_containment_days": 69,
            "ai_security_savings_usd": 1_760_000,
            "breach_lifecycle_savings_per_day": 2_800,
        },
        "regulatory_models": REGULATORY_FINE_MODELS,
    }
