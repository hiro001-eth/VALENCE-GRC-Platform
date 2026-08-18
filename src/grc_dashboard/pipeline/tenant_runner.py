"""Per-tenant isolated metric pipeline execution."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select

from grc_dashboard.config import get_settings
from grc_dashboard.db.models import IntegrationSettings, MetricHistoryRecord, Tenant
from grc_dashboard.db.session import AsyncSessionLocal
from grc_dashboard.pipeline.metrics_formatter import format_dashboard_payload
from grc_dashboard.siem.factory import (
    build_tenant_settings,
    create_siem_client,
    is_siem_configured,
    normalize_siem_type,
)
from grc_dashboard.tenancy.demo_scenarios import build_pipeline_error_state

logger = structlog.get_logger(__name__)


async def load_integration_settings(tenant_id: str) -> IntegrationSettings | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()


async def discover_production_tenant_ids() -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant.id).where(Tenant.is_demo.is_(False))
        )
        return [row[0] for row in result.all()]


def tenant_history_path(tenant_id: str) -> Path:
    return get_settings().pipeline.output_dir / "tenants" / tenant_id / "metrics_history.json"


async def run_tenant_pipeline(tenant_id: str, run_id: str) -> dict[str, Any]:
    """Run an isolated pipeline for one production organization."""
    integration = await load_integration_settings(tenant_id)
    if not is_siem_configured(integration):
        raise ValueError(
            "SIEM not configured. Set Splunk/Elastic credentials in SIEM Connectors "
            "or upload logs via CSV ingestion."
        )

    assert integration is not None
    siem_type = normalize_siem_type(integration.siem_type)
    if siem_type == "CSV":
        return await _run_csv_tenant_pipeline(tenant_id, run_id)

    tenant_settings = build_tenant_settings(integration)
    history_file = tenant_history_path(tenant_id)
    history_file.parent.mkdir(parents=True, exist_ok=True)

    from grc_dashboard.main import run_pipeline_core

    core_result = await run_pipeline_core(
        run_id,
        settings=tenant_settings,
        history_file=history_file,
        siem_client=create_siem_client(tenant_settings),
        skip_pdf=True,
    )
    return format_dashboard_payload(
        tenant_id=tenant_id,
        run_id=run_id,
        definitions=core_result["definitions"],
        metrics=core_result["metrics"],
        rag_assignments=core_result["rag_assignments"],
        narratives=core_result["narratives"],
    )


async def _run_csv_tenant_pipeline(tenant_id: str, run_id: str) -> dict[str, Any]:
    """Build dashboard metrics from uploaded CSV/JSON log ingestion records."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MetricHistoryRecord)
            .where(MetricHistoryRecord.tenant_id == tenant_id)
            .order_by(MetricHistoryRecord.computed_at.desc())
        )
        rows = result.scalars().all()

    if not rows:
        raise ValueError("No uploaded log data found. Upload SIEM logs in Connectors first.")

    latest_by_metric: dict[str, MetricHistoryRecord] = {}
    for row in rows:
        if row.metric_id not in latest_by_metric:
            latest_by_metric[row.metric_id] = row

    metrics = []
    for row in latest_by_metric.values():
        metrics.append({
            "metric_id": row.metric_id,
            "metric_name": row.metric_name or row.metric_id,
            "value": float(row.value),
            "unit": "",
            "rag_status": row.rag_status,
            "ale_usd": int(row.ale_usd or 0),
            "var_95_usd": int(row.var_95_usd or 0),
            "probability_of_breach": float(row.probability_of_breach or 0.1),
            "trend": "stable",
            "narrative": row.narrative or "Derived from uploaded SIEM log ingestion.",
            "computed_at": row.computed_at.isoformat(),
            "run_id": run_id,
            "tenant_id": tenant_id,
        })

    green = sum(1 for m in metrics if m["rag_status"] == "Green")
    amber = sum(1 for m in metrics if m["rag_status"] == "Amber")
    red = sum(1 for m in metrics if m["rag_status"] == "Red")
    overall = "Red" if red else "Amber" if amber else "Green"

    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "is_demo": False,
        "pipeline_status": "ok",
        "data_source": "csv_upload",
        "metrics": metrics,
        "summary": {
            "total_metrics": len(metrics),
            "green": green,
            "amber": amber,
            "red": red,
            "total_ale_usd": sum(m["ale_usd"] for m in metrics),
            "total_var_95_usd": sum(m["var_95_usd"] for m in metrics),
            "overall_rag": overall,
        },
    }


async def run_pipeline_for_tenant_safe(tenant_id: str, run_id: str) -> dict[str, Any]:
    try:
        return await run_tenant_pipeline(tenant_id, run_id)
    except Exception as exc:
        msg = str(exc)
        if "SIEM not configured" in msg:
            logger.info("tenant_pipeline_skipped", tenant_id=tenant_id, reason="siem_not_configured")
        else:
            logger.warning("tenant_pipeline_failed", tenant_id=tenant_id, error=msg)
        return build_pipeline_error_state(tenant_id, run_id, msg)
