"""Regenerate a valid PDF for an existing report record."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from grc_dashboard.config import Settings
from grc_dashboard.db.models import ReportRecord
from grc_dashboard.models.dashboard import DashboardArtifact, PDFMetadata
from grc_dashboard.rendering.pdf_generator import PDFGenerator

logger = structlog.get_logger(__name__)


def pdf_is_valid(path: Path) -> bool:
    try:
        return path.is_file() and path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def repair_report_pdf(row: ReportRecord, settings: Settings) -> Path:
    """Build a real PDF for a completed report (fixes legacy text-as-PDF exports)."""
    run_id = row.run_id
    pdf_path = settings.dashboard.pdf_output_dir / f"dashboard_{run_id}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    generated_at = row.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)

    snapshot_hash = row.snapshot_hash or f"sha256_{run_id[:16]}"
    threshold_hash = row.threshold_hash or f"sha256_{run_id[8:24]}"

    artifact = DashboardArtifact(
        artifact_id=f"art_{run_id}",
        html_path=pdf_path.with_suffix(".html"),
        pdf_path=pdf_path,
        generated_at=generated_at,
        metric_snapshot_hash=snapshot_hash,
        dashboard_run_id=run_id,
    )
    metadata = PDFMetadata(
        dashboard_run_id=run_id,
        generated_at=generated_at,
        metric_snapshot_hash=snapshot_hash,
        threshold_config_hash=threshold_hash,
        siem_query_hashes=[],
    )
    PDFGenerator(settings).generate(artifact, metadata)
    if not pdf_is_valid(pdf_path):
        raise RuntimeError(f"PDF repair failed for run_id={run_id}")
    logger.info("report_pdf_repaired", run_id=run_id, path=str(pdf_path))
    return pdf_path
