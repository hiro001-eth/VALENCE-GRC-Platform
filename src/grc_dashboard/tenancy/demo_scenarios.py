"""Curated real-world-style demo scenarios for the four VALENCE sandbox tenants.

Data is synthetic but modeled on published industry benchmarks (DBIR, SANS SOC Survey,
Ponemon) and typical enterprise GRC postures — not random placeholders.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from grc_dashboard.tenancy.constants import DEMO_TENANT_IDS

TENANT_PROFILES: dict[str, dict[str, str]] = {
    "demo-global-hq": {
        "name": "Meridian Industries — Global HQ",
        "industry": "Manufacturing & Critical Infrastructure",
        "region": "Global",
        "description": (
            "Fortune 500 manufacturer with OT/IT convergence. DORA ICT resilience "
            "pressure; MTTR and CVE lag are primary audit findings."
        ),
    },
    "demo-us-retail": {
        "name": "ShopSmart Retail — North America",
        "industry": "Retail & E-Commerce",
        "region": "United States",
        "description": (
            "2,400-store retail chain. PCI-DSS scope with seasonal breach risk; "
            "POS patching lag and DLP egress alerts dominate the risk register."
        ),
    },
    "demo-eu-fintech": {
        "name": "NordPay Financial — EU Entity",
        "industry": "Financial Services",
        "region": "European Union",
        "description": (
            "Licensed payment institution under DORA/NIS2. Mature SOC with SOAR "
            "playbooks; posture reflects top-quartile peer benchmarks."
        ),
    },
    "demo-healthcare": {
        "name": "CarePoint Health System",
        "industry": "Healthcare",
        "region": "United States",
        "description": (
            "Regional health network (42 facilities). HIPAA Security Rule focus; "
            "privileged access reviews and medical IoT CVE exposure are key KRIs."
        ),
    },
}


def list_demo_tenants() -> list[dict[str, str]]:
    return [
        {"tenant_id": tid, **TENANT_PROFILES[tid]}
        for tid in sorted(DEMO_TENANT_IDS)
    ]


def build_tenant_metrics(tenant_id: str, run_id: str = "VALENCE_DEMO") -> dict[str, Any]:
    """Return a full metrics payload for a demo tenant."""
    now = datetime.now(UTC).isoformat()
    scenarios: dict[str, list[dict[str, Any]]] = {
        "demo-global-hq": [
            _metric("KRI-MTTD-001", "Mean Time to Detect (MTTD)", 14.2, "minutes", "Amber", 182000, 490000, 0.23, "up",
                    "MTTD degraded 12% WoW after OT network sensor rollout. Tune Elastic rules for ICS protocol anomalies."),
            _metric("KRI-MTTR-001", "Mean Time to Respond (MTTR)", 48.7, "minutes", "Red", 610000, 1200000, 0.67, "up",
                    "MTTR exceeds 30-min IR SLA. Tier-1 playbooks lack auto-enrichment for Tier-2 handoff."),
            _metric("KPI-FPR-001", "False Positive Rate (FPR)", 18.4, "%", "Green", 24000, 61000, 0.04, "down",
                    "FPR improved after Sigma rule tuning (Q2). Maintain ML feedback loop."),
            _metric("KRI-CVE-001", "Critical CVE Patch Lag", 8.0, "days", "Red", 890000, 2100000, 0.81, "up",
                    "8 critical CVEs >7 days unpatched on DMZ assets. DORA Art. 6 ICT risk breach imminent."),
            _metric("KPI-PHI-001", "Privileged Access Reviews", 94.1, "%", "Green", 18000, 42000, 0.02, "stable",
                    "Quarterly PAM attestation on track. 3 stale service accounts flagged for deprovisioning."),
            _metric("KRI-DLP-001", "DLP Policy Violations", 37, "incidents", "Amber", 245000, 580000, 0.31, "up",
                    "Engineering GitHub exfil attempts up 22%. Insider threat review opened FIND-2024-017."),
        ],
        "demo-us-retail": [
            _metric("KRI-MTTD-001", "Mean Time to Detect (MTTD)", 24.5, "minutes", "Red", 320000, 850000, 0.42, "up",
                    "Store POS log forwarding latency 18 min avg. Splunk HEC buffer undersized for Black Friday volume."),
            _metric("KRI-MTTR-001", "Mean Time to Respond (MTTR)", 58.2, "minutes", "Red", 740000, 1500000, 0.74, "up",
                    "IR coordinator single point of failure. PCI ROC finding: incident response SLA not met."),
            _metric("KPI-FPR-001", "False Positive Rate (FPR)", 28.1, "%", "Amber", 65000, 120000, 0.08, "up",
                    "Alert fatigue in L1 SOC — 28% FPR vs 15% industry median (Ponemon 2024)."),
            _metric("KRI-CVE-001", "Critical CVE Patch Lag", 14.5, "days", "Red", 1200000, 2800000, 0.89, "up",
                    "CVE-2024-3400 on edge firewalls; change freeze delayed emergency patch window."),
            _metric("KPI-PHI-001", "Privileged Access Reviews", 81.2, "%", "Amber", 84000, 180000, 0.12, "down",
                    "Store manager shared credentials detected in 19% of locations. PAM rollout Phase 2 overdue."),
            _metric("KRI-DLP-001", "DLP Policy Violations", 74, "incidents", "Amber", 480000, 950000, 0.51, "up",
                    "Customer PII egress via personal cloud storage — 74 events this month vs 41 prior."),
        ],
        "demo-eu-fintech": [
            _metric("KRI-MTTD-001", "Mean Time to Detect (MTTD)", 3.4, "minutes", "Green", 12000, 32000, 0.01, "down",
                    "Sub-5-min MTTD via Sentinel UEBA + automated correlation. NIS2 Art. 21 incident detection met."),
            _metric("KRI-MTTR-001", "Mean Time to Respond (MTTR)", 18.2, "minutes", "Green", 45000, 98000, 0.05, "down",
                    "SOAR playbooks contain 94% of L1 incidents. Mean containment 18 min (top decile)."),
            _metric("KPI-FPR-001", "False Positive Rate (FPR)", 8.4, "%", "Green", 8000, 15000, 0.01, "down",
                    "Custom ML classifier reduced FPR from 14% to 8.4% over 6 months."),
            _metric("KRI-CVE-001", "Critical CVE Patch Lag", 2.1, "days", "Green", 68000, 140000, 0.06, "stable",
                    "Immutable infra pipeline; critical CVE SLA 72h with 2.1-day actual mean."),
            _metric("KPI-PHI-001", "Privileged Access Reviews", 98.7, "%", "Green", 5000, 12000, 0.01, "stable",
                    "CyberArk PAM with quarterly attestation. ECB audit clean Q1 2025."),
            _metric("KRI-DLP-001", "DLP Policy Violations", 8, "incidents", "Green", 28000, 65000, 0.03, "down",
                    "Zero high-severity DLP events this quarter. GDPR Art. 32 technical measures evidenced."),
        ],
        "demo-healthcare": [
            _metric("KRI-MTTD-001", "Mean Time to Detect (MTTD)", 19.8, "minutes", "Amber", 265000, 620000, 0.28, "up",
                    "Medical IoT device logs incomplete on 12% of VLANs. Ransomware tabletop exposed detection gaps."),
            _metric("KRI-MTTR-001", "Mean Time to Respond (MTTR)", 42.3, "minutes", "Red", 520000, 1100000, 0.58, "stable",
                    "Clinical workflow constraints delay isolation. HIPAA Security Rule §164.308(a)(6) gap noted."),
            _metric("KPI-FPR-001", "False Positive Rate (FPR)", 22.6, "%", "Amber", 55000, 115000, 0.09, "up",
                    "Epic EHR integration generates high baseline noise. Tuning in progress with vendor."),
            _metric("KRI-CVE-001", "Critical CVE Patch Lag", 11.2, "days", "Red", 980000, 2300000, 0.76, "up",
                    "FDA-regulated imaging systems on extended patch cycle. 14 critical medical IoT CVEs open."),
            _metric("KPI-PHI-001", "Privileged Access Reviews", 76.4, "%", "Red", 195000, 480000, 0.35, "down",
                    "HIPAA minimum necessary review at 76% — below 90% board mandate. 847 stale clinical accounts."),
            _metric("KRI-DLP-001", "DLP Policy Violations", 29, "incidents", "Amber", 310000, 720000, 0.24, "stable",
                    "ePHI email misdelivery incidents stable but above peer median for regional health systems."),
        ],
    }

    metrics = scenarios.get(tenant_id, scenarios["demo-global-hq"])
    for m in metrics:
        m["computed_at"] = now
        m["run_id"] = run_id
        m["tenant_id"] = tenant_id

    overall = _overall_rag(metrics)
    return {
        "run_id": run_id,
        "generated_at": now,
        "tenant_id": tenant_id,
        "is_demo": True,
        "pipeline_status": "demo_curated",
        "metrics": metrics,
        "summary": {
            "total_metrics": len(metrics),
            "green": sum(1 for m in metrics if m["rag_status"] == "Green"),
            "amber": sum(1 for m in metrics if m["rag_status"] == "Amber"),
            "red": sum(1 for m in metrics if m["rag_status"] == "Red"),
            "total_ale_usd": sum(m["ale_usd"] for m in metrics),
            "total_var_95_usd": sum(m["var_95_usd"] for m in metrics),
            "overall_rag": overall,
        },
    }


def build_pipeline_error_state(tenant_id: str, run_id: str, error: str) -> dict[str, Any]:
    """Explicit failure state — no fabricated metrics for production tenants."""
    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "is_demo": False,
        "pipeline_status": "failed",
        "pipeline_error": error,
        "metrics": [],
        "summary": {
            "total_metrics": 0,
            "green": 0,
            "amber": 0,
            "red": 0,
            "total_ale_usd": 0,
            "total_var_95_usd": 0,
            "overall_rag": "Unknown",
        },
    }


def _metric(
    metric_id: str, name: str, value: float, unit: str, rag: str,
    ale: float, var95: float, prob: float, trend: str, narrative: str,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "metric_name": name,
        "value": value,
        "unit": unit,
        "rag_status": rag,
        "ale_usd": ale,
        "var_95_usd": var95,
        "probability_of_breach": prob,
        "trend": trend,
        "narrative": narrative,
    }


def _overall_rag(metrics: list[dict[str, Any]]) -> str:
    if any(m["rag_status"] == "Red" for m in metrics):
        return "Red"
    if any(m["rag_status"] == "Amber" for m in metrics):
        return "Amber"
    return "Green"


def demo_evidence_seed(tenant_id: str) -> list[dict[str, Any]]:
    """Realistic evidence chain entries per demo tenant.

    Each record includes ``control_id`` so that
    ``group_evidence_by_control()`` can link evidence to framework controls.
    """
    _common_metric_evidence: list[tuple[str, str, dict[str, Any], str]] = [
        ("metric_snapshot", "continuous_monitoring", {"metric_id": "KRI-MTTD-001", "control_id": "SOC2-CC7.3", "value": 14.2, "rag_status": "Amber"}, "VALENCE_AUTO_01"),
        ("metric_snapshot", "continuous_monitoring", {"metric_id": "KRI-MTTR-001", "control_id": "DORA-ICT-2.6", "value": 48.7, "rag_status": "Red"}, "VALENCE_AUTO_02"),
        ("metric_snapshot", "continuous_monitoring", {"metric_id": "KPI-FPR-001", "control_id": "SOC2-CC7.1", "value": 18.4, "rag_status": "Green"}, "VALENCE_AUTO_03"),
        ("metric_snapshot", "continuous_monitoring", {"metric_id": "KRI-CVE-001", "control_id": "SOC2-CC7.2", "value": 8.0, "rag_status": "Red"}, "VALENCE_AUTO_04"),
        ("metric_snapshot", "continuous_monitoring", {"metric_id": "KPI-PHI-001", "control_id": "SOC2-CC6.1", "value": 94.1, "rag_status": "Green"}, "VALENCE_AUTO_05"),
        ("metric_snapshot", "continuous_monitoring", {"metric_id": "KRI-DLP-001", "control_id": "SOC2-CC6.6", "value": 37, "rag_status": "Amber"}, "VALENCE_AUTO_06"),
    ]

    base_events: dict[str, list[tuple[str, str, dict[str, Any], str]]] = {
        "demo-global-hq": _common_metric_evidence + [
            ("compliance_check", "audit_evidence", {"framework": "DORA", "control_id": "DORA-ICT-2.6", "title": "Response and Recovery", "status": "Non-Compliant"}, "VALENCE_MFG002"),
            ("compliance_check", "audit_evidence", {"framework": "DORA", "control_id": "DORA-ICT-2.1", "title": "ICT Risk Management Framework", "status": "At Risk"}, "VALENCE_MFG003"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC7.3", "title": "Incident Response", "status": "Non-Compliant"}, "VALENCE_MFG004"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC6.1", "title": "Logical Access Controls", "status": "Compliant"}, "VALENCE_MFG005"),
            ("compliance_check", "audit_evidence", {"framework": "ISO27001", "control_id": "ISO-A.8.8", "title": "Management of technical vulnerabilities", "status": "Non-Compliant"}, "VALENCE_MFG006"),
            ("compliance_check", "audit_evidence", {"framework": "ISO27001", "control_id": "ISO-A.5.24", "title": "Incident management planning", "status": "At Risk"}, "VALENCE_MFG007"),
            ("alert_triggered", "incident_response", {"alert_type": "SLA_BREACH", "metric_id": "KRI-MTTR-001", "control_id": "DORA-ICT-2.6"}, "VALENCE_MFG008"),
            ("access_review", "governance", {"control_id": "SOC2-CC6.3", "scope": "quarterly_PAM", "stale_accounts": 3, "status": "Compliant"}, "VALENCE_MFG009"),
            ("pipeline_execution", "system_health", {"run_id": "VALENCE_DEMO", "metrics_processed": 6, "status": "success"}, "VALENCE_MFG010"),
        ],
        "demo-us-retail": _common_metric_evidence + [
            ("compliance_check", "audit_evidence", {"framework": "PCI_DSS", "control_id": "PCI-6.2", "title": "Patch Management", "status": "Non-Compliant"}, "VALENCE_RET002"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC7.2", "title": "Vulnerability Management", "status": "Non-Compliant"}, "VALENCE_RET003"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC6.6", "title": "Logical Access Security", "status": "At Risk"}, "VALENCE_RET004"),
            ("alert_triggered", "incident_response", {"alert_type": "DLP_EGRESS", "records_affected": 1240, "control_id": "SOC2-CC6.6"}, "VALENCE_RET005"),
            ("access_review", "governance", {"control_id": "SOC2-CC6.1", "scope": "store_manager_credentials", "shared_creds_pct": 19, "status": "Non-Compliant"}, "VALENCE_RET006"),
            ("pipeline_execution", "system_health", {"run_id": "VALENCE_DEMO", "metrics_processed": 6, "status": "success"}, "VALENCE_RET007"),
        ],
        "demo-eu-fintech": _common_metric_evidence + [
            ("compliance_check", "audit_evidence", {"framework": "NIS2", "control_id": "NIS2-Art21", "title": "Incident Detection", "status": "Compliant"}, "VALENCE_FIN002"),
            ("compliance_check", "audit_evidence", {"framework": "DORA", "control_id": "DORA-ICT-2.1", "title": "ICT Risk Management Framework", "status": "Compliant"}, "VALENCE_FIN003"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC6.1", "title": "Logical Access Controls", "status": "Compliant"}, "VALENCE_FIN004"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC7.3", "title": "Incident Response", "status": "Compliant"}, "VALENCE_FIN005"),
            ("compliance_check", "audit_evidence", {"framework": "ISO27001", "control_id": "ISO-A.8.8", "title": "Technical vulnerabilities", "status": "Compliant"}, "VALENCE_FIN006"),
            ("report_generated", "audit_trail", {"report_id": "RPT_ECB_Q1", "type": "pdf", "control_id": "DORA-ICT-2.1"}, "VALENCE_FIN007"),
            ("pipeline_execution", "system_health", {"run_id": "VALENCE_DEMO", "metrics_processed": 6, "status": "success"}, "VALENCE_FIN008"),
        ],
        "demo-healthcare": _common_metric_evidence + [
            ("compliance_check", "audit_evidence", {"framework": "HIPAA", "control_id": "HIPAA-164.308(a)(6)", "title": "Security Incident Procedures", "status": "At Risk"}, "VALENCE_HC002"),
            ("compliance_check", "audit_evidence", {"framework": "HIPAA", "control_id": "HIPAA-164.312(a)(1)", "title": "Access Control", "status": "Non-Compliant"}, "VALENCE_HC003"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC6.1", "title": "Logical Access Controls", "status": "Non-Compliant"}, "VALENCE_HC004"),
            ("compliance_check", "audit_evidence", {"framework": "SOC2", "control_id": "SOC2-CC7.2", "title": "Vulnerability Management", "status": "Non-Compliant"}, "VALENCE_HC005"),
            ("access_review", "governance", {"control_id": "HIPAA-164.312(a)(1)", "stale_accounts": 847, "scope": "clinical", "status": "Non-Compliant"}, "VALENCE_HC006"),
            ("pipeline_execution", "system_health", {"run_id": "VALENCE_DEMO", "metrics_processed": 6, "status": "success"}, "VALENCE_HC007"),
        ],
    }
    return [
        {"event_type": e[0], "category": e[1], "data": e[2], "run_id": e[3]}
        for e in base_events.get(tenant_id, base_events["demo-global-hq"])
    ]


def demo_remediation_seed(tenant_id: str) -> list[dict[str, Any]]:
    """Pre-built remediation tasks per demo tenant so the board is never empty."""
    now = datetime.now(UTC)
    _tasks: dict[str, list[dict[str, Any]]] = {
        "demo-global-hq": [
            {"title": "Remediate DORA ICT-2.6: Response and Recovery SLA breach",
             "description": "MTTR of 48.7 min exceeds 30-min SLA. Add auto-enrichment to Tier-1 IR playbooks and deploy SOAR handoff automation.",
             "owner": "admin", "priority": "critical", "framework": "DORA", "control_id": "DORA-ICT-2.6",
             "due_date": (now + timedelta(hours=48)).isoformat(), "sla_hours": 48, "status": "open"},
            {"title": "Patch 8 critical CVEs on DMZ assets (DORA Art. 6)",
             "description": "CVE-2024-3400, CVE-2024-21762 and 6 others remain unpatched >7 days on edge firewalls. Emergency change window required.",
             "owner": "admin", "priority": "critical", "framework": "DORA", "control_id": "DORA-ICT-2.2",
             "due_date": (now + timedelta(hours=24)).isoformat(), "sla_hours": 24, "status": "open"},
            {"title": "Tune Elastic ICS rules to reduce OT MTTD degradation",
             "description": "MTTD degraded 12% WoW after OT sensor rollout. Sigma rule tuning for ICS protocol anomalies needed.",
             "owner": "admin", "priority": "high", "framework": "SOC2", "control_id": "SOC2-CC7.3",
             "due_date": (now + timedelta(hours=72)).isoformat(), "sla_hours": 72, "status": "in_progress"},
            {"title": "Deprovision 3 stale service accounts from PAM review",
             "description": "Quarterly privileged access attestation flagged 3 stale service accounts. Deprovisioning required per SOC2-CC6.3.",
             "owner": "admin", "priority": "medium", "framework": "SOC2", "control_id": "SOC2-CC6.3",
             "due_date": (now + timedelta(hours=168)).isoformat(), "sla_hours": 168, "status": "open"},
            {"title": "Investigate GitHub exfiltration attempts (DLP-001)",
             "description": "Engineering GitHub exfil attempts up 22%. Insider threat review FIND-2024-017 opened. Review DLP egress policies.",
             "owner": "admin", "priority": "high", "framework": "ISO27001", "control_id": "ISO-A.8.12",
             "due_date": (now + timedelta(hours=72)).isoformat(), "sla_hours": 72, "status": "open"},
        ],
        "demo-us-retail": [
            {"title": "Emergency patch CVE-2024-3400 on edge firewalls",
             "description": "Change freeze delayed emergency patch window. PCI-DSS Req 6.2 non-compliant until patched.",
             "owner": "admin", "priority": "critical", "framework": "PCI_DSS", "control_id": "PCI-6.2",
             "due_date": (now + timedelta(hours=24)).isoformat(), "sla_hours": 24, "status": "open"},
            {"title": "Remediate store manager shared credentials (19% of locations)",
             "description": "PAM Phase 2 rollout overdue. 19% of store locations using shared manager credentials.",
             "owner": "admin", "priority": "critical", "framework": "SOC2", "control_id": "SOC2-CC6.1",
             "due_date": (now + timedelta(hours=48)).isoformat(), "sla_hours": 48, "status": "open"},
            {"title": "Resize Splunk HEC buffer for Black Friday volume",
             "description": "Store POS log forwarding latency 18 min avg. HEC buffer undersized causing MTTD regression.",
             "owner": "admin", "priority": "high", "framework": "SOC2", "control_id": "SOC2-CC7.1",
             "due_date": (now + timedelta(hours=72)).isoformat(), "sla_hours": 72, "status": "in_progress"},
            {"title": "Block personal cloud storage DLP egress",
             "description": "74 customer PII egress events via personal cloud storage this month (vs 41 prior).",
             "owner": "admin", "priority": "high", "framework": "SOC2", "control_id": "SOC2-CC6.6",
             "due_date": (now + timedelta(hours=72)).isoformat(), "sla_hours": 72, "status": "open"},
            {"title": "Address L1 SOC alert fatigue — 28% FPR",
             "description": "False positive rate 28% vs 15% industry median. Sigma rule tuning and ML feedback loop needed.",
             "owner": "admin", "priority": "medium", "framework": "SOC2", "control_id": "SOC2-CC7.5",
             "due_date": (now + timedelta(hours=168)).isoformat(), "sla_hours": 168, "status": "open"},
        ],
        "demo-eu-fintech": [
            {"title": "Update SOAR playbook for PSD2 SCA edge cases",
             "description": "Strong Customer Authentication flow audit found 2 edge cases not covered by current SOAR playbooks.",
             "owner": "admin", "priority": "medium", "framework": "DORA", "control_id": "DORA-ICT-2.6",
             "due_date": (now + timedelta(hours=168)).isoformat(), "sla_hours": 168, "status": "in_progress"},
            {"title": "Renew ECB audit attestation — Q2 preparation",
             "description": "ECB quarterly audit Q2 2025 preparation. Evidence pack generation and review.",
             "owner": "admin", "priority": "low", "framework": "DORA", "control_id": "DORA-ICT-2.1",
             "due_date": (now + timedelta(days=30)).isoformat(), "sla_hours": 720, "status": "open"},
            {"title": "Completed: ML classifier FPR reduction to 8.4%",
             "description": "Custom ML classifier reduced FPR from 14% to 8.4% over 6 months. Closing task.",
             "owner": "admin", "priority": "medium", "framework": "NIS2", "control_id": "NIS2-Art21",
             "due_date": (now - timedelta(days=5)).isoformat(), "sla_hours": 720, "status": "completed"},
        ],
        "demo-healthcare": [
            {"title": "Remediate 847 stale clinical accounts (HIPAA §164.308)",
             "description": "Privileged access review at 76% — below 90% board mandate. 847 stale clinical accounts require deprovisioning.",
             "owner": "admin", "priority": "critical", "framework": "HIPAA", "control_id": "HIPAA-164.312(a)(1)",
             "due_date": (now + timedelta(hours=48)).isoformat(), "sla_hours": 48, "status": "open"},
            {"title": "Patch 14 critical medical IoT CVEs",
             "description": "FDA-regulated imaging systems on extended patch cycle. Coordinate with vendor for emergency maintenance window.",
             "owner": "admin", "priority": "critical", "framework": "HIPAA", "control_id": "HIPAA-164.308(a)(5)",
             "due_date": (now + timedelta(hours=72)).isoformat(), "sla_hours": 72, "status": "open"},
            {"title": "Complete medical IoT VLAN log coverage",
             "description": "Device logs incomplete on 12% of VLANs. Ransomware tabletop exposed detection gaps on imaging subnets.",
             "owner": "admin", "priority": "high", "framework": "HIPAA", "control_id": "HIPAA-164.312(b)",
             "due_date": (now + timedelta(hours=72)).isoformat(), "sla_hours": 72, "status": "in_progress"},
            {"title": "Tune Epic EHR integration alert baseline",
             "description": "EHR integration generates high baseline noise (22.6% FPR). Work with Epic vendor on event filtering.",
             "owner": "admin", "priority": "medium", "framework": "SOC2", "control_id": "SOC2-CC7.1",
             "due_date": (now + timedelta(hours=168)).isoformat(), "sla_hours": 168, "status": "open"},
            {"title": "Review ePHI email misdelivery controls",
             "description": "ePHI email misdelivery incidents stable at 29/month but above peer median for regional health systems.",
             "owner": "admin", "priority": "medium", "framework": "HIPAA", "control_id": "HIPAA-164.312(e)(1)",
             "due_date": (now + timedelta(hours=168)).isoformat(), "sla_hours": 168, "status": "open"},
        ],
    }
    return _tasks.get(tenant_id, _tasks["demo-global-hq"])


def demo_timeline_snapshots(tenant_id: str, days: int = 90) -> list[dict[str, Any]]:
    """Generate realistic trending history from current demo posture."""
    current = build_tenant_metrics(tenant_id)
    snapshots: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for day_offset in range(days, -1, -1):
        ts = now - timedelta(days=day_offset)
        # Slight drift over time toward current values
        factor = 1.0 + (day_offset / days) * 0.08
        metrics = []
        for m in current["metrics"]:
            val = m["value"]
            if m["unit"] == "%" and m["metric_id"] == "KPI-PHI-001":
                val = min(100, val * factor)
            elif m["unit"] in ("minutes", "days", "incidents"):
                val = val * factor
            metrics.append({**m, "value": round(val, 1), "computed_at": ts.isoformat()})
        snapshots.append({
            "snapshot_at": ts.isoformat(),
            "tenant_id": tenant_id,
            "metrics": metrics,
            "summary": _summary_from_metrics(metrics),
        })
    return snapshots


def _summary_from_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_metrics": len(metrics),
        "green": sum(1 for m in metrics if m["rag_status"] == "Green"),
        "amber": sum(1 for m in metrics if m["rag_status"] == "Amber"),
        "red": sum(1 for m in metrics if m["rag_status"] == "Red"),
        "overall_rag": _overall_rag(metrics),
    }
