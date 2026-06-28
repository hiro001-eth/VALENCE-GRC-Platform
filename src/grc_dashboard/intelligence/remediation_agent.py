"""Autonomous compliance remediation agent."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import AuditFinding, EvidenceRequest
from grc_dashboard.db.persistence import append_evidence_record

logger = structlog.get_logger(__name__)
_analyzer = ComplianceGapAnalyzer(FrameworkLoader())


async def auto_remediate_gaps(
    session: AsyncSession,
    tenant_id: str,
    metrics: list[dict[str, Any]],
    username: str,
    max_actions: int = 5,
) -> dict[str, Any]:
    """Create findings, evidence requests, and remediation plans for top gaps."""
    actions: list[dict[str, Any]] = []

    for fw in FrameworkLoader().list_frameworks():
        analysis = _analyzer.analyze_gap(fw, metrics)
        for control in analysis.get("controls", []):
            if control.get("status") not in ("Non-Compliant", "At Risk"):
                continue
            if len(actions) >= max_actions:
                break

            cid = control.get("control_id", "")
            finding_id = f"FIND-AUTO-{uuid.uuid4().hex[:6].upper()}"
            plan = _remediation_plan(control, metrics)

            session.add(
                AuditFinding(
                    id=finding_id,
                    tenant_id=tenant_id,
                    title=f"Auto: {control.get('title', cid)}",
                    description=plan,
                    metric_id=(control.get("metric_ids") or [None])[0],
                    severity="high" if control.get("status") == "Non-Compliant" else "medium",
                    status="assigned",
                    owner_username="analyst",
                    remediation_plan=plan,
                )
            )

            req_id = f"EVREQ-{uuid.uuid4().hex[:8].upper()}"
            session.add(
                EvidenceRequest(
                    id=req_id,
                    tenant_id=tenant_id,
                    framework=fw,
                    control_id=cid,
                    title=f"Evidence for {cid}",
                    description=plan,
                    requested_by=username,
                    assignee="analyst",
                    due_at=datetime.now(UTC) + timedelta(days=7),
                    status="pending",
                )
            )

            await append_evidence_record(
                session,
                tenant_id,
                event_type="auto_remediation",
                category="audit_evidence",
                data={
                    "finding_id": finding_id,
                    "evidence_request_id": req_id,
                    "control_id": cid,
                    "framework": fw,
                    "plan": plan,
                },
                run_id="AUTO_REMEDIATE",
            )

            actions.append({
                "framework": fw,
                "control_id": cid,
                "finding_id": finding_id,
                "evidence_request_id": req_id,
                "remediation_plan": plan,
            })

    await session.commit()
    logger.info("auto_remediation_complete", tenant_id=tenant_id, actions=len(actions))
    return {
        "actions_taken": len(actions),
        "actions": actions,
        "message": f"Created {len(actions)} findings and evidence requests with remediation plans.",
    }


def _remediation_plan(control: dict[str, Any], metrics: list[dict[str, Any]]) -> str:
    mids = control.get("metric_ids", [])
    red = [m for m in metrics if m.get("metric_id") in mids and m.get("rag_status") == "Red"]
    if red:
        names = ", ".join(m.get("metric_name", m.get("metric_id", "")) for m in red[:3])
        return (
            f"1. Assign owner for {control.get('control_id')}. "
            f"2. Remediate red metrics: {names}. "
            f"3. Upload evidence to vault within 7 days. "
            f"4. Re-run pipeline to verify green status."
        )
    return (
        f"Review control {control.get('control_id')} ({control.get('title')}). "
        f"Tighten thresholds, update SIEM rules, and attach audit evidence."
    )
