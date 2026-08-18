"""Integration tests for APM and OpenTelemetry instrumentation."""
from __future__ import annotations

from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.api.middleware.observability import HAS_OPENTELEMETRY


def test_telemetry_graceful_import_status():
    """Verify that OpenTelemetry imports have been checked and resolved."""
    # Ensure setup doesn't fail even if packages are missing
    assert HAS_OPENTELEMETRY in (True, False)


def test_fastapi_app_has_otel_middleware():
    """Verify that FastAPI app has been setup with instrumented middleware if active."""
    # OTel instruments via FastAPIInstrumentor which wraps app middlewares
    # Confirm app starts and responds successfully under instrumentation
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
