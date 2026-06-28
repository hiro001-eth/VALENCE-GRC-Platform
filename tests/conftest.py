"""Shared pytest fixtures — isolate rate limits and use a dedicated test database."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

_test_db = Path(tempfile.gettempdir()) / f"valence_pytest_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db}"
os.environ["VALENCE_ENV"] = "development"
os.environ["PYTEST_CURRENT_TEST"] = "1"
os.environ.setdefault("VALENCE_SKIP_PIPELINE_SCHEDULER", "1")

from grc_dashboard.auth import rate_limit  # noqa: E402


@pytest.fixture(autouse=True)
def reset_rate_limit_state(monkeypatch):
    """Prevent 429 responses when many tests log in as admin."""
    monkeypatch.setattr(rate_limit, "LOGIN_RATE_LIMIT", 1000)
    monkeypatch.setattr(rate_limit, "LOCKOUT_THRESHOLD", 100)
    rate_limit._memory_counters.clear()
    monkeypatch.setattr(rate_limit.session_store, "_redis_client", None)
    yield
    rate_limit._memory_counters.clear()


@pytest.fixture
def unique_registration_payload() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "company_name": f"Test Corp {suffix}",
        "admin_username": f"testadmin_{suffix}",
        "admin_email": f"testadmin_{suffix}@testcorp.example",
        "admin_password": "securepass123",
        "admin_full_name": "Test Admin",
    }
