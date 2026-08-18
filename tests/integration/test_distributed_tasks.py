"""Integration tests for distributed background tasks."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grc_dashboard.db.session import init_db
from grc_dashboard.worker import generate_pdf_report_task
from tests.security import admin_headers


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


def test_celery_task_fallback_eager():
    """Verify that Celery is in eager/sync fallback mode during test runs."""
    # Our worker file configures task_always_eager = True automatically in test mode
    assert generate_pdf_report_task.app.conf.task_always_eager is True


def test_report_generation_dispatches_celery_task(client: TestClient):
    """Verify that the /generate route successfully dispatches the Celery task."""
    headers = admin_headers(client)
    res = client.post(
        "/api/reports/generate",
        headers=headers,
        json={"title": "Celery Integration Test Report"},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "generating"
    assert "report_id" in body
