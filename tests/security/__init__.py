"""Shared security test fixtures for VALENCE GRC Platform.

Provides authentication helpers, malicious payload generators, and
multi-tenant test setup utilities used across all security test modules.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.db.session import init_db


@pytest.fixture(scope="module", autouse=True)
async def _security_db():
    """Ensure database is initialized for the security test session."""
    await init_db()


@pytest.fixture
def client():
    """Fresh TestClient per test."""
    with TestClient(app) as c:
        yield c


# ---------- Auth helpers ----------

def get_auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    """Login and return Authorization headers."""
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def admin_headers(client: TestClient) -> dict[str, str]:
    return get_auth_headers(client, "admin", "valence123")


def ciso_headers(client: TestClient) -> dict[str, str]:
    return get_auth_headers(client, "ciso", "ciso123")


def analyst_headers(client: TestClient) -> dict[str, str]:
    return get_auth_headers(client, "analyst", "analyst123")


def auditor_headers(client: TestClient) -> dict[str, str]:
    return get_auth_headers(client, "auditor", "auditor123")


def get_token(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    return res.json()["access_token"]


# ---------- Malicious payloads ----------

SQL_INJECTION_PAYLOADS = [
    "' OR 1=1 --",
    "'; DROP TABLE users; --",
    "\" OR \"\"=\"",
    "1; SELECT * FROM users",
    "admin'--",
    "' UNION SELECT NULL, NULL, NULL --",
    "1' AND 1=(SELECT COUNT(*) FROM users) --",
    "' OR 'x'='x",
]

XSS_PAYLOADS = [
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert('XSS')>",
    "javascript:alert('XSS')",
    "<svg onload=alert('XSS')>",
    "'\"><script>alert(document.cookie)</script>",
    "<iframe src=\"javascript:alert('XSS')\">",
    "{{7*7}}",  # Template injection
    "${7*7}",   # Expression injection
]

PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\config\\sam",
    "....//....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..%252f..%252f..%252fetc%252fpasswd",
]

COMMAND_INJECTION_PAYLOADS = [
    "; ls -la",
    "| cat /etc/passwd",
    "$(whoami)",
    "`id`",
    "&& echo vulnerable",
]

HEADER_INJECTION_PAYLOADS = [
    "value\r\nInjected-Header: malicious",
    "value\nSet-Cookie: stolen=true",
    "value\r\nX-Custom: injected",
]

OVERSIZED_PAYLOADS = [
    "A" * 10_000,
    "A" * 100_000,
    "A" * 1_000_000,
]

# ---------- Unique entity generators ----------

def unique_username() -> str:
    return f"test_{uuid.uuid4().hex[:8]}"


def unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:8]}@security-test.example"
