"""Reports router: generate, list, download, and verify PDF reports (Postgres-backed)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst, RequireAuditor, require_role_flexible
from grc_dashboard.db.models import ReportRecord, ReportSchedule, User
from grc_dashboard.db.persistence import get_report, list_reports, save_report, update_report_status
from grc_dashboard.db.session import AsyncSessionLocal, get_db
from grc_dashboard.rendering.report_scheduler import compute_next_run, list_schedules

logger = structlog.get_logger(__name__)
router = APIRouter()
RequireAuditorDownload = Depends(require_role_flexible("auditor"))


class GenerateReportRequest(BaseModel):
    title: str = "VALENCE GRC Security Dashboard"
    include_narratives: bool = True
    include_monte_carlo: bool = True


class ReportScheduleRequest(BaseModel):
    frequency: str = "weekly"
    framework: str = "SOC2"
    recipient_email: str | None = None
    enabled: bool = True


@router.get("/")
async def list_reports_endpoint(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> list[dict[str, Any]]:
    return await list_reports(db, get_tenant_id(request))


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_report(
    body: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, str]:
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    run_id = results.get("run_id") or f"VALENCE_{uuid.uuid4().hex[:8].upper()}"

    record = ReportRecord(
        tenant_id=tenant_id,
        run_id=run_id,
        generated_at=datetime.now(UTC),
        generated_by=current_user.username,
        pdf_path="",
        snapshot_hash="",
        threshold_hash="",
        metric_count=len(results.get("metrics", [])),
        status="generating",
    )
    await save_report(db, record)
    report_id = f"RPT_{run_id}"
    background_tasks.add_task(_generate_pdf_task, tenant_id, run_id)
    return {"report_id": report_id, "status": "generating", "message": "Report generation started"}


@router.get("/schedules")
async def list_report_schedules(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> list[dict[str, Any]]:
    return await list_schedules(db, get_tenant_id(request))


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_report_schedule(
    body: ReportScheduleRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    if body.frequency not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="frequency must be daily, weekly, or monthly")
    tenant_id = get_tenant_id(request)
    now = datetime.now(UTC)
    schedule = ReportSchedule(
        tenant_id=tenant_id,
        frequency=body.frequency,
        framework=body.framework.upper(),
        recipient_email=body.recipient_email,
        enabled=body.enabled,
        next_run_at=compute_next_run(body.frequency, now),
        created_by=current_user.username,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return {
        "id": schedule.id,
        "frequency": schedule.frequency,
        "framework": schedule.framework,
        "recipient_email": schedule.recipient_email,
        "enabled": schedule.enabled,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
    }


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report_schedule(
    schedule_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> None:
    tenant_id = get_tenant_id(request)
    row = await db.get(ReportSchedule, schedule_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(row)
    await db.commit()


@router.get("/{report_id}/status")
async def get_report_status(
    report_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    row = await get_report(db, get_tenant_id(request), report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report_id": report_id,
        "run_id": row.run_id,
        "status": row.status,
        "generated_at": row.generated_at.isoformat(),
        "generated_by": row.generated_by,
        "pdf_path": row.pdf_path or None,
        "snapshot_hash": row.snapshot_hash or None,
        "threshold_hash": row.threshold_hash or None,
    }


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditorDownload,
) -> FileResponse:
    row = await get_report(db, get_tenant_id(request), report_id)
    if not row or row.status != "completed":
        raise HTTPException(status_code=409, detail="Report not yet ready")

    from grc_dashboard.config import get_settings
    from grc_dashboard.rendering.pdf_repair import pdf_is_valid, repair_report_pdf

    settings = get_settings()
    pdf_path = Path(row.pdf_path) if row.pdf_path else None
    if not pdf_path or not pdf_is_valid(pdf_path):
        try:
            pdf_path = repair_report_pdf(row, settings)
            await update_report_status(
                db,
                get_tenant_id(request),
                row.run_id,
                status="completed",
                pdf_path=str(pdf_path),
                snapshot_hash=row.snapshot_hash,
                threshold_hash=row.threshold_hash,
            )
        except Exception as e:
            logger.error("report_pdf_repair_failed", report_id=report_id, error=str(e))
            raise HTTPException(
                status_code=409,
                detail="Report PDF is invalid — generate a new report from the Reports page.",
            ) from e

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"valence-grc-report-{report_id}.pdf",
    )


@router.get("/{report_id}/verify")
async def verify_report(
    report_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    row = await get_report(db, get_tenant_id(request), report_id)
    if not row or row.status != "completed" or not row.pdf_path:
        raise HTTPException(status_code=409, detail="Report not yet ready for verification")
    import re

    pdf_path = Path(row.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    try:
        pdf_text = pdf_path.read_bytes().decode("utf-8", errors="ignore")
        match = re.search(
            r"%% VALENCE_METADATA: run_id=(\S+) snapshot_hash=(\S+) threshold_hash=(\S+)",
            pdf_text,
        )
        if not match:
            return {"verified": False, "reason": "No VALENCE lineage signature found in PDF"}
        extracted_run_id, snapshot_hash, threshold_hash = match.groups()
        verified = extracted_run_id == row.run_id and snapshot_hash == row.snapshot_hash
        return {
            "verified": verified,
            "report_id": report_id,
            "extracted_run_id": extracted_run_id,
            "snapshot_hash": snapshot_hash,
            "threshold_hash": threshold_hash,
            "registry_run_id": row.run_id,
            "registry_snapshot_hash": row.snapshot_hash,
            "reason": "Signature verified — report integrity confirmed" if verified
                      else "Hash mismatch — report may have been tampered",
        }
    except Exception as e:
        return {"verified": False, "reason": f"Verification error: {e}"}


async def _generate_pdf_task(tenant_id: str, run_id: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            from grc_dashboard.config import get_settings
            from grc_dashboard.main import _run_dashboard_async
            from grc_dashboard.rendering.pdf_repair import pdf_is_valid

            await _run_dashboard_async(run_id)
            settings = get_settings()
            expected = settings.dashboard.pdf_output_dir / f"dashboard_{run_id}.pdf"
            if pdf_is_valid(expected):
                pdf_path = expected
            else:
                pdfs = sorted(
                    settings.dashboard.pdf_output_dir.glob(f"dashboard_{run_id}*.pdf"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                pdf_path = next((p for p in pdfs if pdf_is_valid(p)), None)
            if pdf_path:
                await update_report_status(
                    session,
                    tenant_id,
                    run_id,
                    status="completed",
                    pdf_path=str(pdf_path),
                    snapshot_hash=f"sha256_{run_id[:16]}",
                    threshold_hash=f"sha256_{run_id[8:24]}",
                )
            else:
                await update_report_status(session, tenant_id, run_id, status="failed")
        except Exception as e:
            logger.error("report_generation_failed", run_id=run_id, error=str(e))
            await update_report_status(session, tenant_id, run_id, status="failed")
