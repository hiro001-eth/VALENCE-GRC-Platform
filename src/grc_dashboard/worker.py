"""Celery Distributed background compute worker context."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog

try:
    from celery import Celery
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False
    class CeleryMock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.conf = {}
        def task(self, *args: Any, **kwargs: Any) -> Any:
            def decorator(fn: Any) -> Any:
                fn.delay = fn
                return fn
            return decorator
    Celery = CeleryMock  # type: ignore[misc,assignment]

logger = structlog.get_logger(__name__)

# Config Celery using Redis URL environment variable
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()

# Create Celery app
celery_app = Celery("valence", broker=REDIS_URL, backend=REDIS_URL)

# Fallback to sync execution (always eager) during testing or if requested
IS_TESTING = (
    os.getenv("VALENCE_ENV", "").lower() in {"test", "testing"}
    or "pytest" in __import__("sys").modules
    or bool(os.getenv("PYTEST_CURRENT_TEST"))
    or os.getenv("VALENCE_CELERY_SYNC", "false").lower() in {"true", "1", "yes"}
)

if HAS_CELERY:
    celery_app.conf.update(
        task_always_eager=IS_TESTING,
        task_eager_propagates=IS_TESTING,
        result_expires=3600,
    )


@celery_app.task(name="valence.generate_pdf_report")
def generate_pdf_report_task(tenant_id: str, run_id: str) -> dict[str, Any]:
    """Celery background task to render compliance report PDF using WeasyPrint."""
    logger.info("celery_generating_pdf_report", tenant_id=tenant_id, run_id=run_id)

    # Resolve async db and execution within a sync wrapper for Celery compatibility
    async def run():
        from grc_dashboard.config import get_settings
        from grc_dashboard.db.persistence import update_report_status
        from grc_dashboard.db.session import AsyncSessionLocal
        from grc_dashboard.main import _run_dashboard_async
        from grc_dashboard.rendering.pdf_repair import pdf_is_valid

        async with AsyncSessionLocal() as session:
            try:
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
                    logger.info("celery_pdf_report_completed", run_id=run_id, pdf_path=str(pdf_path))
                    return {"status": "completed", "pdf_path": str(pdf_path)}
                else:
                    await update_report_status(session, tenant_id, run_id, status="failed")
                    logger.error("celery_pdf_report_not_found", run_id=run_id)
                    return {"status": "failed", "reason": "PDF not generated/valid"}
            except Exception as e:
                logger.error("celery_pdf_report_error", run_id=run_id, error=str(e))
                await update_report_status(session, tenant_id, run_id, status="failed")
                return {"status": "failed", "error": str(e)}

    # Run the coroutine in a separate thread with a new event loop to avoid deadlocks
    # when run synchronously inside a running event loop (e.g. eager mode in tests).
    from concurrent.futures import ThreadPoolExecutor

    def run_in_new_loop():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(run())
        finally:
            loop.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_new_loop)
        return future.result()
