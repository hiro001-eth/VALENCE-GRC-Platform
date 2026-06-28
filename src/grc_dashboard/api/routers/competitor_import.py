"""Import controls from Vanta, Drata, or CSV exports."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin
from grc_dashboard.db.models import RemediationTask, User
from grc_dashboard.db.session import get_db

router = APIRouter()

VANTA_COLUMNS = {"control", "control_id", "framework", "status", "owner", "test"}
DRATA_COLUMNS = {"control_name", "requirement", "framework", "status", "owner"}


def _detect_format(headers: set[str]) -> str:
    h = {x.lower().strip() for x in headers}
    if h & VANTA_COLUMNS:
        return "vanta"
    if h & DRATA_COLUMNS:
        return "drata"
    return "generic"


@router.post("/vanta-csv")
async def import_vanta_csv(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Import Vanta/Drata control export CSV into remediation tasks."""
    tenant_id = get_tenant_id(request)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="Empty CSV")

    fmt = _detect_format(set(reader.fieldnames))
    created = 0
    for row in reader:
        title = (
            row.get("control")
            or row.get("control_id")
            or row.get("control_name")
            or row.get("requirement")
            or ""
        ).strip()
        if not title:
            continue
        status = (row.get("status") or "").lower()
        if status in ("passing", "pass", "compliant", "ok"):
            continue
        framework = row.get("framework") or row.get("standard") or "imported"
        owner = row.get("owner") or current_user.username
        task = RemediationTask(
            id=f"REM-{uuid.uuid4().hex[:8].upper()}",
            tenant_id=tenant_id,
            title=f"[{fmt.upper()}] {title[:200]}",
            description=f"Imported from {file.filename} — status: {row.get('status', 'gap')}",
            owner=owner,
            priority="high" if status in ("failing", "fail", "critical") else "medium",
            status="open",
            framework=str(framework)[:50],
            control_id=str(row.get("control_id") or row.get("id") or "")[:50] or None,
            sla_hours=72,
        )
        db.add(task)
        created += 1
        if created >= 100:
            break

    await db.commit()
    return {
        "format_detected": fmt,
        "imported": created,
        "message": f"Created {created} remediation tasks from {fmt} export",
    }
