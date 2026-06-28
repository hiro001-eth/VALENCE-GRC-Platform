"""Automated evidence recording from pipeline runs — closes the audit loop."""
from __future__ import annotations

from typing import Any

import structlog

from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

_loader = FrameworkLoader()
_analyzer = ComplianceGapAnalyzer(_loader)


async def record_pipeline_evidence(
    tenant_id: str,
    run_id: str,
    metrics: list[dict[str, Any]],
) -> int:
    """Persist metric snapshots and compliance checks into the evidence vault."""
    if not metrics:
        return 0

    recorded = 0
    async with AsyncSessionLocal() as session:
        for metric in metrics:
            await append_evidence_record(
                session,
                tenant_id,
                event_type="metric_snapshot",
                category="continuous_monitoring",
                data={
                    "metric_id": metric.get("metric_id"),
                    "value": metric.get("value"),
                    "rag_status": metric.get("rag_status"),
                    "ale_usd": metric.get("ale_usd", 0),
                },
                run_id=run_id,
            )
            recorded += 1

        for fw in _loader.list_frameworks():
            analysis = _analyzer.analyze_gap(fw, metrics)
            for control in analysis.get("controls", []):
                status = control.get("status", "")
                if status in ("Compliant", "No Data"):
                    continue
                await append_evidence_record(
                    session,
                    tenant_id,
                    event_type="compliance_check",
                    category="audit_evidence",
                    data={
                        "framework": fw,
                        "control_id": control.get("control_id"),
                        "control": str(control.get("control_id", "")).split("-")[-1],
                        "title": control.get("title"),
                        "status": status,
                    },
                    run_id=run_id,
                )
                recorded += 1

        await append_evidence_record(
            session,
            tenant_id,
            event_type="pipeline_execution",
            category="system_health",
            data={
                "run_id": run_id,
                "metrics_processed": len(metrics),
                "status": "success",
            },
            run_id=run_id,
        )
        recorded += 1

    logger.info("pipeline_evidence_recorded", tenant_id=tenant_id, run_id=run_id, count=recorded)
    return recorded
