"""Playwright end-to-end smoke tests for VALENCE frontend."""
from __future__ import annotations

import os
import subprocess
import time

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("VALENCE_E2E_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session", autouse=True)
def ensure_server() -> None:
  if os.getenv("VALENCE_E2E_EXTERNAL", "").lower() in {"1", "true", "yes"}:
    return
  proc = subprocess.Popen(
    ["python", "-m", "uvicorn", "grc_dashboard.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
    env={**os.environ, "VALENCE_SKIP_PIPELINE_SCHEDULER": "true", "VALENCE_ENV": "test"},
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )
  for _ in range(40):
    try:
      import httpx

      if httpx.get(f"{BASE_URL}/api/health", timeout=2).status_code == 200:
        break
    except Exception:
      time.sleep(0.5)
  yield
  proc.terminate()


def test_health_endpoint() -> None:
  import httpx

  res = httpx.get(f"{BASE_URL}/api/health", timeout=10)
  assert res.status_code == 200
  assert res.json()["status"] == "ok"


def test_login_page_loads(page: Page) -> None:
  page.goto(BASE_URL)
  expect(page.locator("#login-view")).to_be_visible()
  expect(page.locator("#login-username")).to_be_visible()


def test_demo_login_shows_dashboard(page: Page) -> None:
  page.goto(BASE_URL)
  page.fill("#login-username", "admin")
  page.fill("#login-password", os.getenv("VALENCE_DEMO_PASSWORD", "ValenceDemo2026!"))
  page.click("#login-submit")
  page.wait_for_timeout(2000)
  expect(page.locator("#app-shell")).to_be_visible(timeout=15000)
