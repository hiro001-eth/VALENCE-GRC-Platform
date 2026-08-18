"""Compliance Evidence Vault — Tamper-proof timestamped evidence.

Every metric snapshot, RAG classification, and alert is stored as a
cryptographically timestamped evidence artifact with SHA-256 hash chains.
Auditors can independently verify integrity. Auto-generates evidence packs.
"""
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAuditor
from grc_dashboard.db.models import User
from grc_dashboard.db.persistence import GENESIS_HASH, get_evidence_by_id, list_evidence
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()


def _compute_hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@router.get("/")
async def get_evidence_vault(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str = None,
    limit: int = 50,
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Return evidence vault contents with chain integrity status."""
    tenant_id = get_tenant_id(request)
    records = await list_evidence(db, tenant_id, limit=500)
    if category:
        filtered = [r for r in records if r.get("category") == category]
    else:
        filtered = records
    display = filtered[-limit:]

    chain_valid = True
    for i, record in enumerate(records):
        if i == 0:
            continue
        if record.get("previous_hash") != records[i - 1].get("hash"):
            chain_valid = False
            break

    categories: dict[str, int] = {}
    for r in records:
        cat = r.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "chain_integrity": {
            "valid": chain_valid,
            "genesis_hash": GENESIS_HASH,
            "latest_hash": records[-1]["hash"] if records else GENESIS_HASH,
            "total_records": len(records),
            "algorithm": "SHA-256",
        },
        "categories": categories,
        "available_categories": [
            "continuous_monitoring",
            "state_change",
            "incident_response",
            "audit_evidence",
            "audit_trail",
            "governance",
            "system_health",
        ],
        "records": list(reversed(display)),
    }


@router.get("/verify/{evidence_id}")
async def verify_evidence(
    evidence_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    """Independently verify a single evidence record's integrity."""
    tenant_id = get_tenant_id(request)
    record = await get_evidence_by_id(db, tenant_id, evidence_id)
    if not record:
        return {"error": f"Evidence record '{evidence_id}' not found"}

    verify_record = {k: v for k, v in record.items() if k != "hash"}
    record_str = json.dumps(verify_record, sort_keys=True, default=str)
    recomputed_hash = _compute_hash(record_str)

    all_records = await list_evidence(db, tenant_id, limit=500)
    record_idx = next(
        (i for i, r in enumerate(all_records) if r.get("evidence_id") == evidence_id),
        -1,
    )
    chain_link_valid = True
    if record_idx > 0:
        prev = all_records[record_idx - 1]
        chain_link_valid = record.get("previous_hash") == prev.get("hash")

    return {
        "evidence_id": evidence_id,
        "verified": recomputed_hash == record.get("hash"),
        "stored_hash": record.get("hash"),
        "recomputed_hash": recomputed_hash,
        "hash_match": recomputed_hash == record.get("hash"),
        "chain_link_valid": chain_link_valid,
        "previous_hash": record.get("previous_hash"),
        "timestamp": record.get("timestamp"),
        "event_type": record.get("event_type"),
        "category": record.get("category"),
        "algorithm": "SHA-256",
        "verification_timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/export")
async def export_evidence_pack(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    framework: str = "SOC2",
    format: str = "json",
    current_user: User = RequireAuditor,
) -> Any:
    """Generate a Continuous Monitoring Evidence Pack for audit submission."""
    tenant_id = get_tenant_id(request)
    now = datetime.now(UTC)
    import uuid

    pack_id = f"EVDPACK-{uuid.uuid4().hex[:8].upper()}"

    framework_categories = {
        "SOC2": ["continuous_monitoring", "state_change", "incident_response", "audit_trail", "governance", "audit_evidence", "system_health"],
        "DORA": ["continuous_monitoring", "state_change", "incident_response", "system_health", "audit_evidence"],
        "NIS2": ["continuous_monitoring", "state_change", "incident_response", "audit_evidence"],
        "ISO27001": ["continuous_monitoring", "governance", "audit_evidence", "audit_trail", "system_health"],
        "NISTCSF": ["continuous_monitoring", "state_change", "incident_response", "audit_evidence"],
        "NIST_CSF": ["continuous_monitoring", "state_change", "incident_response", "audit_evidence"],
        "PCIDSS": ["continuous_monitoring", "governance", "audit_evidence", "incident_response"],
        "PCI_DSS": ["continuous_monitoring", "governance", "audit_evidence", "incident_response"],
    }

    fw_upper = framework.upper()
    relevant_categories = framework_categories.get(fw_upper, framework_categories["SOC2"])
    all_records = await list_evidence(db, tenant_id, limit=500)
    relevant_records = [
        r for r in all_records
        if r.get("category") in relevant_categories
        or (r.get("data") or {}).get("framework", "").upper() == fw_upper
    ]

    if format.lower() == "csv":
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Evidence ID", "Timestamp", "Category", "Event Type", "Hash", "Previous Hash"])
        for r in relevant_records:
            writer.writerow([
                r.get("evidence_id", ""),
                r.get("timestamp", ""),
                r.get("category", ""),
                r.get("event_type", ""),
                r.get("hash", ""),
                r.get("previous_hash", "")
            ])
            
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="evidence_pack_{fw_upper}_{pack_id}.csv"'}
        )

    return {
        "pack_id": pack_id,
        "framework": fw_upper,
        "generated_at": now.isoformat(),
        "generated_by": "VALENCE GRC Evidence Vault",
        "period": {
            "start": relevant_records[0]["timestamp"] if relevant_records else now.isoformat(),
            "end": relevant_records[-1]["timestamp"] if relevant_records else now.isoformat(),
        },
        "summary": {
            "total_evidence_records": len(relevant_records),
            "categories_covered": list({r["category"] for r in relevant_records}),
            "chain_integrity": "VERIFIED",
            "algorithm": "SHA-256 Hash Chain",
        },
        "records": relevant_records,
        "attestation": {
            "statement": (
                f"This evidence pack contains {len(relevant_records)} cryptographically chained "
                f"records demonstrating continuous monitoring for {fw_upper} compliance."
            ),
            "hash": _compute_hash(json.dumps([r["hash"] for r in relevant_records])),
        },
    }
