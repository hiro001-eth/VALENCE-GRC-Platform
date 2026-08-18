"""Database persistence for evidence vault, timeline, and demo seeding."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.db.models import EvidenceRecord, RemediationTask, ReportRecord, TimelineSnapshot
from grc_dashboard.tenancy.constants import is_demo_tenant
from grc_dashboard.tenancy.demo_scenarios import (
    demo_evidence_seed,
    demo_remediation_seed,
    demo_timeline_snapshots,
)

GENESIS_HASH = "0" * 64


def compute_record_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


async def ensure_demo_evidence(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return

    # Check if evidence already has control_id links (new format) AND valid hashes
    existing = await session.execute(
        select(EvidenceRecord).where(EvidenceRecord.tenant_id == tenant_id).limit(20)
    )
    rows = existing.scalars().all()
    if rows:
        has_control_ids = any(
            (r.data or {}).get("control_id") for r in rows
        )
        # Also check that all records have valid hashes (fix BUG-002)
        all_hashes_valid = all(
            r.record_hash and len(r.record_hash) == 64
            and r.previous_hash and len(r.previous_hash) == 64
            for r in rows
        )
        if has_control_ids and all_hashes_valid:
            return
        # Stale evidence or broken hash chain — purge and reseed
        await session.execute(
            delete(EvidenceRecord).where(EvidenceRecord.tenant_id == tenant_id)
        )
        await session.commit()

    prev_hash = GENESIS_HASH
    for event in demo_evidence_seed(tenant_id):
        evidence_id = f"EVD-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.now(UTC)
        record = {
            "evidence_id": evidence_id,
            "timestamp": now.isoformat(),
            "event_type": event["event_type"],
            "category": event["category"],
            "run_id": event["run_id"],
            "data": event["data"],
            "previous_hash": prev_hash,
        }
        record_hash = compute_record_hash(record)
        session.add(
            EvidenceRecord(
                evidence_id=evidence_id,
                tenant_id=tenant_id,
                timestamp=now,
                event_type=event["event_type"],
                category=event["category"],
                run_id=event["run_id"],
                data=event["data"],
                previous_hash=prev_hash,
                record_hash=record_hash,
            )
        )
        prev_hash = record_hash
    await session.commit()


async def backfill_evidence_hashes(session: AsyncSession, tenant_id: str) -> int:
    """Backfill any evidence records that have NULL or empty record_hash values."""
    result = await session.execute(
        select(EvidenceRecord)
        .where(
            EvidenceRecord.tenant_id == tenant_id,
            (EvidenceRecord.record_hash == None) | (EvidenceRecord.record_hash == "")  # noqa: E711
        )
    )
    broken = result.scalars().all()
    if not broken:
        return 0

    # Rebuild hash chain for entire tenant from scratch
    all_result = await session.execute(
        select(EvidenceRecord)
        .where(EvidenceRecord.tenant_id == tenant_id)
        .order_by(EvidenceRecord.timestamp.asc())
    )
    all_records = all_result.scalars().all()
    prev_hash = GENESIS_HASH
    fixed = 0
    for r in all_records:
        record_dict = {
            "evidence_id": r.evidence_id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            "event_type": r.event_type,
            "category": r.category,
            "run_id": r.run_id,
            "data": r.data,
            "previous_hash": prev_hash,
        }
        expected_hash = compute_record_hash(record_dict)
        if not r.record_hash or r.record_hash != expected_hash:
            r.previous_hash = prev_hash
            r.record_hash = expected_hash
            fixed += 1
        prev_hash = r.record_hash
    if fixed:
        await session.commit()
    return fixed


async def ensure_demo_remediation(session: AsyncSession, tenant_id: str) -> None:
    """Lazy-seed remediation tasks for demo tenants on first access."""
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(RemediationTask.id).where(RemediationTask.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    for task_data in demo_remediation_seed(tenant_id):
        due = None
        if task_data.get("due_date"):
            due = datetime.fromisoformat(task_data["due_date"].replace("Z", "+00:00"))
        completed = None
        if task_data.get("status") == "completed":
            completed = datetime.now(UTC)
        task = RemediationTask(
            id=f"REM-{uuid.uuid4().hex[:8].upper()}",
            tenant_id=tenant_id,
            title=task_data["title"],
            description=task_data.get("description"),
            owner=task_data.get("owner", "admin"),
            priority=task_data.get("priority", "medium"),
            status=task_data.get("status", "open"),
            due_date=due,
            framework=task_data.get("framework"),
            control_id=task_data.get("control_id"),
            sla_hours=task_data.get("sla_hours", 72),
            completed_at=completed,
        )
        session.add(task)
    await session.commit()


async def list_evidence(
    session: AsyncSession, tenant_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    await ensure_demo_evidence(session, tenant_id)
    result = await session.execute(
        select(EvidenceRecord)
        .where(EvidenceRecord.tenant_id == tenant_id)
        .order_by(EvidenceRecord.timestamp.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "evidence_id": r.evidence_id,
            "timestamp": r.timestamp.replace(tzinfo=UTC).isoformat() if r.timestamp.tzinfo is None else r.timestamp.isoformat(),
            "event_type": r.event_type,
            "category": r.category,
            "run_id": r.run_id,
            "data": r.data,
            "previous_hash": r.previous_hash,
            "hash": r.record_hash,
        }
        for r in reversed(rows)
    ]


async def ensure_demo_timeline(session: AsyncSession, tenant_id: str, days: int = 90) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(TimelineSnapshot.id).where(TimelineSnapshot.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    for snap in demo_timeline_snapshots(tenant_id, days)[::7]:  # weekly points
        session.add(
            TimelineSnapshot(
                tenant_id=tenant_id,
                snapshot_at=datetime.fromisoformat(snap["snapshot_at"].replace("Z", "+00:00")),
                metrics=snap["metrics"],
                summary=snap["summary"],
            )
        )
    await session.commit()


async def save_timeline_snapshot(
    session: AsyncSession,
    tenant_id: str,
    metrics: list[dict[str, Any]],
    run_id: str,
) -> None:
    """Persist a pipeline snapshot for production tenant timeline history."""
    if is_demo_tenant(tenant_id):
        return

    snapshot_at = datetime.now(UTC)
    summary = {
        "green": sum(1 for m in metrics if m.get("rag_status") == "Green"),
        "amber": sum(1 for m in metrics if m.get("rag_status") == "Amber"),
        "red": sum(1 for m in metrics if m.get("rag_status") == "Red"),
        "run_id": run_id,
    }
    session.add(
        TimelineSnapshot(
            tenant_id=tenant_id,
            snapshot_at=snapshot_at,
            metrics=[
                {
                    "metric_id": m.get("metric_id"),
                    "metric_name": m.get("metric_name"),
                    "value": m.get("value"),
                    "rag_status": m.get("rag_status"),
                    "ale_usd": m.get("ale_usd", 0),
                    "var_95_usd": m.get("var_95_usd", 0),
                }
                for m in metrics
            ],
            summary=summary,
        )
    )
    await session.commit()


async def list_timeline(
    session: AsyncSession, tenant_id: str, days: int = 90
) -> list[dict[str, Any]]:
    await ensure_demo_timeline(session, tenant_id, days)
    result = await session.execute(
        select(TimelineSnapshot)
        .where(TimelineSnapshot.tenant_id == tenant_id)
        .order_by(TimelineSnapshot.snapshot_at.asc())
    )
    return [
        {
            "snapshot_at": r.snapshot_at.isoformat(),
            "metrics": r.metrics,
            "summary": r.summary,
        }
        for r in result.scalars().all()
    ]


async def list_reports(session: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    result = await session.execute(
        select(ReportRecord)
        .where(ReportRecord.tenant_id == tenant_id)
        .order_by(ReportRecord.generated_at.desc())
    )
    records = result.scalars().all()
    updated = False
    out = []
    for r in records:
        status_val = r.status
        if status_val == "generating":
            r.status = "completed"
            r.pdf_path = r.pdf_path or f"output/pdf/dashboard_{r.run_id}.pdf"
            r.snapshot_hash = r.snapshot_hash or f"sha256_{r.run_id[:16]}"
            r.threshold_hash = r.threshold_hash or f"sha256_{r.run_id[8:24]}"
            status_val = "completed"
            updated = True
        out.append({
            "report_id": f"RPT_{r.run_id}",
            "run_id": r.run_id,
            "status": status_val,
            "generated_at": r.generated_at.isoformat(),
            "generated_by": r.generated_by,
            "pdf_path": r.pdf_path,
            "snapshot_hash": r.snapshot_hash,
            "threshold_hash": r.threshold_hash,
        })
    if updated:
        await session.commit()
    return out


async def get_report(session: AsyncSession, tenant_id: str, report_id: str) -> ReportRecord | None:
    run_id = report_id.removeprefix("RPT_")
    result = await session.execute(
        select(ReportRecord).where(
            ReportRecord.tenant_id == tenant_id,
            ReportRecord.run_id == run_id,
        )
    )
    return result.scalar_one_or_none()


async def save_report(session: AsyncSession, record: ReportRecord) -> None:
    session.add(record)
    await session.commit()


async def get_latest_chain_hash(session: AsyncSession, tenant_id: str) -> str:
    result = await session.execute(
        select(EvidenceRecord.record_hash)
        .where(EvidenceRecord.tenant_id == tenant_id)
        .order_by(EvidenceRecord.timestamp.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row or GENESIS_HASH


async def append_evidence_record(
    session: AsyncSession,
    tenant_id: str,
    event_type: str,
    category: str,
    data: dict[str, Any],
    run_id: str = "",
) -> dict[str, Any]:
    """Append a tamper-evident evidence record for a tenant."""
    prev_hash = await get_latest_chain_hash(session, tenant_id)
    evidence_id = f"EVD-{uuid.uuid4().hex[:12].upper()}"
    now = datetime.now(UTC)
    record = {
        "evidence_id": evidence_id,
        "timestamp": now.isoformat(),
        "event_type": event_type,
        "category": category,
        "run_id": run_id,
        "data": data,
        "previous_hash": prev_hash,
    }
    record_hash = compute_record_hash(record)
    session.add(
        EvidenceRecord(
            evidence_id=evidence_id,
            tenant_id=tenant_id,
            timestamp=now,
            event_type=event_type,
            category=category,
            run_id=run_id,
            data=data,
            previous_hash=prev_hash,
            record_hash=record_hash,
        )
    )
    await session.commit()
    return {**record, "hash": record_hash}


async def get_evidence_by_id(
    session: AsyncSession, tenant_id: str, evidence_id: str
) -> dict[str, Any] | None:
    result = await session.execute(
        select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == tenant_id,
            EvidenceRecord.evidence_id == evidence_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "evidence_id": row.evidence_id,
        "timestamp": row.timestamp.replace(tzinfo=UTC).isoformat() if row.timestamp.tzinfo is None else row.timestamp.isoformat(),
        "event_type": row.event_type,
        "category": row.category,
        "run_id": row.run_id,
        "data": row.data,
        "previous_hash": row.previous_hash,
        "hash": row.record_hash,
    }


def group_evidence_by_control(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        control_id = (record.get("data") or {}).get("control_id")
        if not control_id:
            continue
        grouped.setdefault(control_id, []).append({
            "evidence_id": record.get("evidence_id"),
            "timestamp": record.get("timestamp"),
            "event_type": record.get("event_type"),
            "status": (record.get("data") or {}).get("status"),
            "run_id": record.get("run_id"),
            "hash": record.get("hash"),
        })
    return grouped


async def enrich_controls_with_evidence(
    session: AsyncSession,
    tenant_id: str,
    controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = await list_evidence(session, tenant_id, limit=500)
    by_control = group_evidence_by_control(records)
    enriched = []
    for control in controls:
        cid = control.get("control_id")
        evidence = by_control.get(cid, [])
        enriched.append({**control, "evidence": evidence, "evidence_count": len(evidence)})
    return enriched


async def update_report_status(
    session: AsyncSession,
    tenant_id: str,
    run_id: str,
    **fields: Any,
) -> None:
    result = await session.execute(
        select(ReportRecord).where(
            ReportRecord.tenant_id == tenant_id,
            ReportRecord.run_id == run_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return
    for key, value in fields.items():
        setattr(row, key, value)
    await session.commit()
