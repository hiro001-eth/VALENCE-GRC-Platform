"""Metrics router: current state, history, summary."""
from typing import Any

import structlog
from fastapi import APIRouter, Request

from grc_dashboard.api.tenant_context import get_tenant_results
from grc_dashboard.auth.dependencies import RequireAuditor
from grc_dashboard.db.models import User

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/")
async def get_metrics(
    request: Request,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Return the latest computed metrics with RAG status and financial risk."""
    results: dict[str, Any] = get_tenant_results(request)
    return {
        "run_id": results.get("run_id", ""),
        "generated_at": results.get("generated_at", ""),
        "metrics": results.get("metrics", []),
    }


@router.get("/summary")
async def get_summary(
    request: Request,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Return aggregate dashboard summary: RAG counts, total ALE/VaR."""
    results: dict[str, Any] = get_tenant_results(request)
    return results.get("summary", {
        "total_metrics": 0,
        "green": 0,
        "amber": 0,
        "red": 0,
        "total_ale_usd": 0,
        "total_var_95_usd": 0,
        "overall_rag": "NoData",
    })


@router.get("/latest")
async def get_latest_metrics(
    request: Request,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Return the latest computed metrics with RAG status and financial risk."""
    results: dict[str, Any] = get_tenant_results(request)
    return {
        "run_id": results.get("run_id", ""),
        "generated_at": results.get("generated_at", ""),
        "metrics": results.get("metrics", []),
    }


@router.get("/{metric_id}")
async def get_metric_detail(
    metric_id: str,
    request: Request,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Return detail for a single metric including narrative and risk profile."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    for m in metrics:
        if m.get("metric_id") == metric_id:
            return m
    return {"error": f"Metric '{metric_id}' not found"}
