"""Integration tests for enterprise roadmap APIs."""
import io

import pytest
from fastapi.testclient import TestClient

from grc_dashboard.api.main import app
from grc_dashboard.db.session import init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


def _admin_headers(client: TestClient) -> dict[str, str]:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "valence123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_command_center_posture():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        res = client.get("/api/command-center/posture", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "headline" in data
        assert "chains" in data


def test_global_search():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        res = client.get("/api/search/?q=access", headers=headers)
        assert res.status_code == 200
        assert "results" in res.json()


def test_billing_plans_and_checkout_demo():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        plans = client.get("/api/billing/plans", headers=headers)
        assert plans.status_code == 200
        assert "growth" in plans.json()["plans"]

        checkout = client.post(
            "/api/billing/checkout",
            headers=headers,
            json={"plan": "growth"},
        )
        assert checkout.status_code == 200
        assert checkout.json()["mode"] == "demo"


def test_billing_webhook_demo_mode():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        # Ensure tenant exists and can be updated.
        sub = client.get("/api/billing/subscription", headers=headers)
        assert sub.status_code == 200

        payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_demo_123",
                    "subscription": "sub_demo_123",
                    "metadata": {"tenant_id": "demo-global-hq", "plan": "enterprise"},
                }
            },
        }
        res = client.post("/api/billing/webhook", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        dup = client.post("/api/billing/webhook", json=payload)
        assert dup.status_code == 200
        assert dup.json()["status"] == "duplicate"


def test_msp_portfolio():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        res = client.get("/api/msp/portfolio", headers=headers)
        assert res.status_code == 200
        assert "portfolio" in res.json()


def test_competitor_csv_import():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        csv_body = "control,framework,status,owner\nAccess reviews,SOC2,failing,grc-lead\n"
        res = client.post(
            "/api/import/vanta-csv",
            headers=headers,
            files={"file": ("vanta.csv", io.BytesIO(csv_body.encode()), "text/csv")},
        )
        assert res.status_code == 200
        assert res.json()["imported"] >= 1


def test_questionnaire_approval_flow():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        submit = client.post("/api/questionnaires/submit-for-approval", headers=headers)
        assert submit.status_code == 200
        assert submit.json()["status"] == "pending_approval"

        approve = client.post("/api/questionnaires/approve", headers=headers)
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"


def test_remediation_and_search_after_schema_sync():
    """Regression: missing columns on remediation_tasks broke search + compliance."""
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "valence123"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        remediation = client.get("/api/remediation/", headers=headers)
        assert remediation.status_code == 200, remediation.text

        search = client.get("/api/search/?q=access", headers=headers)
        assert search.status_code == 200, search.text
        assert "results" in search.json()


def test_aws_iam_role_connect():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        res = client.post(
            "/api/integrations/hub/aws-iam-role",
            headers=headers,
            json={"role_arn": "arn:aws:iam::123456789012:role/ValenceReadOnly", "external_id": "valence-ext-id-001"},
        )
        assert res.status_code == 200
        assert res.json()["auth_method"] == "iam_role"


def test_oauth_connections_endpoint():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        res = client.get("/api/integrations/oauth/connections", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert "providers" in body


def test_change_management_workflow():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/workflows/change-requests",
            headers=headers,
            json={
                "title": "Deploy SIEM parser update",
                "description": "Parser version bump",
                "change_type": "infra",
                "risk_level": "medium",
            },
        )
        assert created.status_code == 201
        cid = created.json()["id"]

        listed = client.get("/api/workflows/change-requests", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == cid for item in listed.json()["change_requests"])

        approved = client.post(f"/api/workflows/change-requests/{cid}/approve", headers=headers, json={})
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        implemented = client.post(
            f"/api/workflows/change-requests/{cid}/implement",
            headers=headers,
            json={"implementation_notes": "Deployment successful"},
        )
        assert implemented.status_code == 200
        assert implemented.json()["status"] == "implemented"


def test_chatops_query_endpoint():
    with TestClient(app) as client:
        headers = _admin_headers(client)
        status = client.get("/api/chatops/status", headers=headers)
        assert status.status_code == 200
        q = client.post("/api/chatops/query", headers=headers, json={"query": "What is our compliance score?"})
        assert q.status_code == 200
        assert "answer" in q.json()


def _slack_signed_headers(secret: str, body: str) -> dict[str, str]:
    import hashlib
    import hmac
    import time

    ts = str(int(time.time()))
    base = f"v0:{ts}:{body}"
    sig = "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def test_chatops_slack_command_bridge(monkeypatch):
    secret = "test-signing-secret"
    monkeypatch.setenv("SLACK_SIGNING_SECRET", secret)
    monkeypatch.setenv("CHATOPS_WEBHOOK_DEV_MODE", "false")
    monkeypatch.setenv("CHATOPS_DEFAULT_TENANT_ID", "demo-global-hq")

    body = "token=x&team_id=T1&team_domain=acme&channel_id=C1&user_id=U1&command=%2Fvalence&text=compliance+score"
    headers = _slack_signed_headers(secret, body)

    with TestClient(app) as client:
        resp = client.post("/api/chatops/slack/command", content=body, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert data["response_type"] == "ephemeral"
        assert "Compliance" in data["text"] or "compliance" in data["text"].lower()


def test_chatops_slack_command_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "real-secret")
    monkeypatch.setenv("CHATOPS_WEBHOOK_DEV_MODE", "false")

    body = "command=%2Fvalence&text=help"
    headers = _slack_signed_headers("wrong-secret", body)

    with TestClient(app) as client:
        resp = client.post("/api/chatops/slack/command", content=body, headers=headers)
        assert resp.status_code == 401


def test_chatops_teams_message_bridge(monkeypatch):
    secret = "teams-webhook-secret"
    monkeypatch.setenv("CHATOPS_TEAMS_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("CHATOPS_WEBHOOK_DEV_MODE", "false")
    monkeypatch.setenv("CHATOPS_DEFAULT_TENANT_ID", "demo-global-hq")

    with TestClient(app) as client:
        resp = client.post(
            "/api/chatops/teams/message",
            headers={"X-ChatOps-Secret": secret},
            json={"text": "top risk exposure"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "message"
        assert "text" in data
        assert "exposure" in data["text"].lower() or "risk" in data["text"].lower()
