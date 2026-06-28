"""Format pipeline computation results into dashboard API payloads."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from grc_dashboard.models.metric import MetricDefinition, MetricValue
from grc_dashboard.models.rag import RAGAssignment


def format_dashboard_payload(
    *,
    tenant_id: str,
    run_id: str,
    definitions: list[MetricDefinition],
    metrics: list[MetricValue],
    rag_assignments: list[RAGAssignment],
    narratives: dict[str, str],
) -> dict[str, Any]:
    rag_by_id = {r.metric_id: r for r in rag_assignments}
    def_by_id = {d.metric_id: d for d in definitions}

    formatted: list[dict[str, Any]] = []
    for metric in metrics:
        defn = def_by_id.get(metric.metric_id)
        rag = rag_by_id.get(metric.metric_id)
        rag_status = rag.rag_status if rag else "Amber"
        ale = float(rag.annualized_loss_expectancy_usd if rag else metric.ale_usd or 0)
        var95 = float(rag.var_95_usd if rag else metric.var_95_usd or ale * 2.5)
        formatted.append({
            "metric_id": metric.metric_id,
            "metric_name": defn.metric_name if defn else metric.metric_id,
            "value": float(metric.value),
            "unit": defn.unit if defn else "",
            "rag_status": rag_status,
            "ale_usd": int(ale),
            "var_95_usd": int(var95),
            "probability_of_breach": float(metric.probability_of_breach or 0.1),
            "trend": "stable",
            "narrative": narratives.get(metric.metric_id, ""),
            "computed_at": metric.computed_at.isoformat() if metric.computed_at else datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "tenant_id": tenant_id,
            "is_stale": metric.is_stale,
        })

    now = datetime.now(UTC).isoformat()
    overall = "Green"
    if any(m["rag_status"] == "Red" for m in formatted):
        overall = "Red"
    elif any(m["rag_status"] == "Amber" for m in formatted):
        overall = "Amber"

    return {
        "run_id": run_id,
        "generated_at": now,
        "tenant_id": tenant_id,
        "is_demo": False,
        "pipeline_status": "ok",
        "metrics": formatted,
        "summary": {
            "total_metrics": len(formatted),
            "green": sum(1 for m in formatted if m["rag_status"] == "Green"),
            "amber": sum(1 for m in formatted if m["rag_status"] == "Amber"),
            "red": sum(1 for m in formatted if m["rag_status"] == "Red"),
            "total_ale_usd": sum(m["ale_usd"] for m in formatted),
            "total_var_95_usd": sum(m["var_95_usd"] for m in formatted),
            "overall_rag": overall,
        },
    }
