"""Continuous control monitoring — automated tests (Vanta/Drata-style CCM)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import IntegrationSettings, User
from grc_dashboard.db.session import get_db
from grc_dashboard.siem.factory import is_siem_configured, normalize_siem_type
from grc_dashboard.tenancy.constants import is_demo_tenant
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

router = APIRouter()
_loader = FrameworkLoader()
_analyzer = ComplianceGapAnalyzer(_loader)

# Core automated tests mapped to compliance + SIEM signals (expandable catalog).
AUTOMATED_TEST_DEFS: list[dict[str, Any]] = [
    {
        "id": "CCM-SIEM-001",
        "name": "SIEM ingestion active",
        "category": "logging",
        "frameworks": ["SOC2", "ISO27001", "NIST_CSF"],
        "metric_id": "MTTD",
        "description": "Security events are collected and MTTD is within SLA.",
    },
    {
        "id": "CCM-IR-002",
        "name": "Incident response MTTR",
        "category": "incident_response",
        "frameworks": ["SOC2", "HIPAA", "NIS2"],
        "metric_id": "MTTR",
        "description": "Mean time to remediate incidents meets target.",
    },
    {
        "id": "CCM-VULN-003",
        "name": "Vulnerability patch cadence",
        "category": "vulnerability",
        "frameworks": ["SOC2", "PCI_DSS", "ISO27001"],
        "metric_id": "VULN_PATCH_LAG",
        "description": "Critical CVE patch lag within policy threshold.",
    },
    {
        "id": "CCM-ID-004",
        "name": "MFA coverage",
        "category": "identity",
        "frameworks": ["SOC2", "ISO27001", "HIPAA"],
        "metric_id": "MFA_COVERAGE",
        "description": "Multi-factor authentication enforced for workforce accounts.",
    },
    {
        "id": "CCM-ENC-005",
        "name": "Encryption coverage",
        "category": "data_protection",
        "frameworks": ["SOC2", "HIPAA", "GDPR"],
        "metric_id": "ENCRYPTION_COVERAGE",
        "description": "Data at rest and in transit encryption controls.",
    },
    {
        "id": "CCM-PHISH-006",
        "name": "Phishing resilience",
        "category": "awareness",
        "frameworks": ["SOC2", "ISO27001"],
        "metric_id": "PHISHING_CLICK_RATE",
        "description": "Security awareness training effectiveness.",
    },
    {
        "id": "CCM-CONFIG-007",
        "name": "Alert channel configured",
        "category": "operations",
        "frameworks": ["SOC2", "DORA"],
        "metric_id": None,
        "integration_check": "slack_or_teams",
        "description": "Incident notification webhooks are configured.",
    },
    {
        "id": "CCM-PENTEST-008",
        "name": "Annual penetration test",
        "category": "assessment",
        "frameworks": ["SOC2", "PCI_DSS"],
        "metric_id": "PENTEST_FINDINGS",
        "description": "External penetration test findings tracked and remediated.",
    },
]


def _metric_map(metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {m.get("metric_id", ""): m for m in metrics}


def _evaluate_test(
    test: dict[str, Any],
    metrics_by_id: dict[str, dict[str, Any]],
    settings: IntegrationSettings | None,
    demo: bool,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    integration_check = test.get("integration_check")
    if integration_check == "slack_or_teams":
        configured = bool(
            settings
            and (settings.slack_webhook_url or settings.teams_webhook_url)
        )
        status = "passing" if configured or demo else "failing"
        return {
            **test,
            "status": status,
            "last_run": now,
            "evidence_source": "integration_settings" if configured else "not_configured",
            "detail": "Alert webhook configured." if configured else "Configure Slack or Teams in Connectors.",
        }

    metric_id = test.get("metric_id")
    metric = metrics_by_id.get(metric_id or "")
    if not metric:
        return {
            **test,
            "status": "pending" if not demo else "passing",
            "last_run": now,
            "evidence_source": "sandbox_demo" if demo else "awaiting_pipeline",
            "detail": "Awaiting SIEM pipeline run." if not demo else "Sandbox scenario data.",
        }

    rag = metric.get("rag_status", "Amber")
    status = "passing" if rag == "Green" else ("at_risk" if rag == "Amber" else "failing")
    return {
        **test,
        "status": status,
        "last_run": now,
        "evidence_source": "siem_pipeline",
        "current_value": metric.get("value"),
        "rag_status": rag,
        "detail": metric.get("narrative", f"{metric_id} is {rag}."),
    }


@router.get("/tests")
async def list_control_tests(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Continuous control monitoring dashboard — automated test library."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics = results.get("metrics", []) if results else []
    metrics_by_id = _metric_map(metrics)

    settings_res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = settings_res.scalar_one_or_none()
    demo = is_demo_tenant(tenant_id)

    tests = [
        _evaluate_test(t, metrics_by_id, settings, demo)
        for t in AUTOMATED_TEST_DEFS
    ]
    passing = sum(1 for t in tests if t["status"] == "passing")
    failing = sum(1 for t in tests if t["status"] == "failing")
    at_risk = sum(1 for t in tests if t["status"] == "at_risk")
    pending = sum(1 for t in tests if t["status"] == "pending")

    siem_configured = is_siem_configured(settings) or demo or (
        settings and normalize_siem_type(settings.siem_type or "") == "CSV"
    )

    return {
        "tenant_id": tenant_id,
        "monitored_at": datetime.now(UTC).isoformat(),
        "siem_configured": siem_configured,
        "summary": {
            "total": len(tests),
            "passing": passing,
            "failing": failing,
            "at_risk": at_risk,
            "pending": pending,
            "health_pct": round((passing / len(tests)) * 100, 1) if tests else 0,
        },
        "tests": tests,
        "competitive_note": (
            "VALENCE CCM binds SIEM-native metrics to framework controls — "
            "continuous monitoring with financial risk (ALE/VaR), not checkbox audits alone."
        ),
    }


@router.get("/summary")
async def control_monitoring_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    data = await list_control_tests(request, db, current_user)
    return {
        "health_pct": data["summary"]["health_pct"],
        "failing": data["summary"]["failing"],
        "at_risk": data["summary"]["at_risk"],
        "total": data["summary"]["total"],
    }
