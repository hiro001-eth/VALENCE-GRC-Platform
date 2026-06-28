"""Industry benchmarking — versioned reference datasets with full provenance."""
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from grc_dashboard.api.tenant_context import get_tenant_results
from grc_dashboard.auth.dependencies import require_feature
from grc_dashboard.benchmarking.loader import (
    LOWER_IS_BETTER,
    calculate_percentile,
    get_industry_benchmarks,
    load_benchmark_catalog,
)
from grc_dashboard.db.models import User

router = APIRouter()


@router.get("/")
async def get_benchmarks(
    request: Request,
    industry: str = Query(default="Financial Services"),
    current_user: User = Depends(require_feature("benchmarking")),
) -> dict[str, Any]:
    """Return industry benchmarking data for all current metrics."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    catalog = load_benchmark_catalog()
    benchmarks = get_industry_benchmarks(industry)

    comparisons = []
    for m in metrics:
        mid = m.get("metric_id", "")
        value = m.get("value", 0)
        bench = benchmarks.get(mid)
        if not bench:
            continue

        lower_better = LOWER_IS_BETTER.get(mid, True)
        percentile = calculate_percentile(value, bench, lower_better)

        if percentile >= 75:
            assessment, assessment_icon = "Excellent", "🏆"
        elif percentile >= 50:
            assessment, assessment_icon = "Above Average", "✅"
        elif percentile >= 25:
            assessment, assessment_icon = "Below Average", "⚠️"
        else:
            assessment, assessment_icon = "Critical Gap", "🚨"

        gap_to_median = round(value - bench["p50"], 2)
        gap_direction = (
            "better"
            if (lower_better and gap_to_median < 0) or (not lower_better and gap_to_median > 0)
            else "worse"
        )

        comparisons.append({
            "metric_id": mid,
            "metric_name": m.get("metric_name", mid),
            "your_value": value,
            "unit": bench["unit"],
            "industry_p25": bench["p25"],
            "industry_p50": bench["p50"],
            "industry_p75": bench["p75"],
            "industry_p90": bench["p90"],
            "your_percentile": percentile,
            "assessment": assessment,
            "assessment_icon": assessment_icon,
            "gap_to_median": abs(gap_to_median),
            "gap_direction": gap_direction,
            "source": bench["source"],
            "lower_is_better": lower_better,
        })

    avg_percentile = sum(c["your_percentile"] for c in comparisons) / max(1, len(comparisons))
    excellent_count = sum(1 for c in comparisons if c["your_percentile"] >= 75)
    critical_count = sum(1 for c in comparisons if c["your_percentile"] < 25)

    return {
        "industry": industry,
        "available_industries": list(catalog["industries"].keys()),
        "catalog_version": catalog["version"],
        "catalog_last_updated": catalog["last_updated"],
        "methodology": catalog["methodology"],
        "overall_score": {
            "average_percentile": round(avg_percentile),
            "grade": (
                "A" if avg_percentile >= 80 else "B" if avg_percentile >= 60
                else "C" if avg_percentile >= 40 else "D" if avg_percentile >= 20 else "F"
            ),
            "excellent_metrics": excellent_count,
            "critical_gaps": critical_count,
            "total_metrics": len(comparisons),
        },
        "comparisons": comparisons,
        "data_provenance": {
            "type": "curated_reference_dataset",
            "note": (
                "Percentiles are derived from published industry research (DBIR, SANS, Ponemon, "
                "CrowdStrike). Live peer benchmarking APIs are on the enterprise roadmap."
            ),
            "sources": sorted({c["source"] for c in comparisons}),
        },
    }
