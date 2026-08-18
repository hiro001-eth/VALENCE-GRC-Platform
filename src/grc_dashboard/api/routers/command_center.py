"""Command center — SIEM metric → control → financial risk (VALENCE moat)."""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import User

router = APIRouter()
_analyzer = ComplianceGapAnalyzer(FrameworkLoader())


def _severity_color(rag: str) -> str:
    return {"Red": "#ef4444", "Amber": "#f59e0b", "Green": "#22c55e"}.get(rag, "#94a3b8")


def _risk_tier(ale: float) -> str:
    if ale >= 500_000:
        return "critical"
    if ale >= 200_000:
        return "high"
    if ale >= 50_000:
        return "medium"
    return "low"


@router.get("/posture")
async def command_center_posture(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Unified SIEM → control → ALE view for executive and sales demos."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", []) if results else []
    summary = results.get("summary", {}) if results else {}

    # ── Build enriched risk chains ──
    chains = []
    for m in metrics[:12]:
        metric_id = m.get("metric_id", "")
        related = []
        for fw in ("SOC2", "ISO27001", "NIST_CSF", "HIPAA", "DORA"):
            analysis = _analyzer.analyze_gap(fw, metrics)
            for ctrl in analysis.get("controls", []):
                if metric_id in ctrl.get("metric_ids", []):
                    related.append({
                        "framework": fw,
                        "control_id": ctrl.get("control_id"),
                        "title": ctrl.get("title", "")[:80],
                        "status": ctrl.get("status"),
                    })
        ale = m.get("ale_usd", 0)
        var95 = m.get("var_95_usd", 0)
        rag = m.get("rag_status", "Amber")
        chains.append({
            "metric_id": metric_id,
            "metric_name": m.get("metric_name"),
            "value": m.get("value"),
            "unit": m.get("unit", ""),
            "rag_status": rag,
            "ale_usd": ale,
            "var_95_usd": var95,
            "risk_tier": _risk_tier(ale),
            "controls": related[:6],
            "control_count": len(related),
            "sla_status": "breached" if rag == "Red" else ("at_risk" if rag == "Amber" else "within_sla"),
            "remediation_hint": (
                "Immediate remediation required — SLA breach detected"
                if rag == "Red"
                else (
                    "Action recommended — approaching SLA threshold"
                    if rag == "Amber"
                    else "Operational — within acceptable tolerance"
                )
            ),
            "trend_7d": round(random.uniform(-15, 15), 1),
        })

    # ── Compute aggregated stats ──
    total_ale = summary.get("total_ale_usd") or sum(x.get("ale_usd") or 0 for x in metrics)
    total_var = sum(x.get("var_95_usd") or 0 for x in metrics)
    red_count = sum(1 for x in metrics if x.get("rag_status") == "Red")
    amber_count = sum(1 for x in metrics if x.get("rag_status") == "Amber")
    green_count = sum(1 for x in metrics if x.get("rag_status") == "Green")
    total_metrics = len(metrics)
    overall_rag = summary.get("overall_rag", "—")

    # ── RAG distribution for donut chart ──
    rag_distribution = {
        "red": red_count,
        "amber": amber_count,
        "green": green_count,
        "total": total_metrics,
    }

    # ── Top 5 risk exposures sorted by ALE ──
    top_risks = sorted(chains, key=lambda c: c.get("ale_usd", 0), reverse=True)[:5]

    # ── Simulated active incidents ──
    now = datetime.now(UTC)
    active_incidents = [
        {
            "id": "INC-2026-0847",
            "title": "Elevated privilege escalation attempts on production IAM",
            "severity": "critical",
            "detected_at": (now - timedelta(hours=2, minutes=14)).isoformat(),
            "source": "Okta + AWS CloudTrail",
            "status": "investigating",
            "mttr_estimate_hrs": 4.2,
            "assigned_to": "SOC Team Alpha",
        },
        {
            "id": "INC-2026-0846",
            "title": "DLP policy violations — bulk data download from S3",
            "severity": "high",
            "detected_at": (now - timedelta(hours=6, minutes=42)).isoformat(),
            "source": "AWS GuardDuty",
            "status": "containment",
            "mttr_estimate_hrs": 2.8,
            "assigned_to": "IR Lead",
        },
        {
            "id": "INC-2026-0845",
            "title": "Anomalous login pattern from geo-impossible travel",
            "severity": "medium",
            "detected_at": (now - timedelta(hours=11, minutes=8)).isoformat(),
            "source": "Azure AD + Okta",
            "status": "monitoring",
            "mttr_estimate_hrs": 1.5,
            "assigned_to": "Identity Team",
        },
    ]

    # ── SLA compliance metrics ──
    sla_metrics = {
        "mttd_target_hrs": 1.0,
        "mttd_actual_hrs": 0.8,
        "mttd_status": "passing",
        "mttr_target_hrs": 4.0,
        "mttr_actual_hrs": 5.2,
        "mttr_status": "breached",
        "patch_sla_target_days": 7,
        "patch_sla_actual_days": 8,
        "patch_sla_status": "breached",
        "uptime_target_pct": 99.9,
        "uptime_actual_pct": 99.7,
        "uptime_status": "at_risk",
    }

    # ── Threat vector heatmap data ──
    threat_vectors = [
        {"vector": "Phishing / Social Engineering", "frequency": 847, "severity": "high", "trend": "increasing", "blocked_pct": 96.2},
        {"vector": "Credential Stuffing", "frequency": 2341, "severity": "medium", "trend": "stable", "blocked_pct": 99.1},
        {"vector": "Ransomware Delivery", "frequency": 12, "severity": "critical", "trend": "decreasing", "blocked_pct": 100.0},
        {"vector": "Insider Threat (Anomalous)", "frequency": 37, "severity": "high", "trend": "increasing", "blocked_pct": 78.4},
        {"vector": "API Abuse / Scraping", "frequency": 1204, "severity": "medium", "trend": "increasing", "blocked_pct": 94.7},
        {"vector": "Supply Chain Compromise", "frequency": 3, "severity": "critical", "trend": "stable", "blocked_pct": 100.0},
    ]

    # ── Control effectiveness scores ──
    control_effectiveness = {
        "identity_access": {"score": 87, "trend": 2.4, "label": "Identity & Access"},
        "data_protection": {"score": 72, "trend": -3.1, "label": "Data Protection"},
        "incident_response": {"score": 64, "trend": -8.2, "label": "Incident Response"},
        "vulnerability_mgmt": {"score": 58, "trend": 5.6, "label": "Vulnerability Mgmt"},
        "endpoint_security": {"score": 91, "trend": 1.2, "label": "Endpoint Security"},
        "network_security": {"score": 83, "trend": 0.8, "label": "Network Security"},
        "logging_monitoring": {"score": 79, "trend": -1.4, "label": "Logging & Monitoring"},
        "bcp_dr": {"score": 55, "trend": -4.7, "label": "BCP / DR"},
    }

    return {
        "tenant_id": tenant_id,
        "generated_at": now.isoformat(),
        "headline": {
            "total_ale_usd": total_ale,
            "total_var_95_usd": total_var,
            "red_metrics": red_count,
            "amber_metrics": amber_count,
            "green_metrics": green_count,
            "total_metrics": total_metrics,
            "overall_rag": overall_rag,
            "data_mode": "live" if metrics else "awaiting_pipeline",
            "risk_score": round(100 - (green_count / max(total_metrics, 1) * 100), 1),
        },
        "rag_distribution": rag_distribution,
        "chains": chains,
        "top_risks": top_risks,
        "active_incidents": active_incidents,
        "sla_metrics": sla_metrics,
        "threat_vectors": threat_vectors,
        "control_effectiveness": control_effectiveness,
    }
