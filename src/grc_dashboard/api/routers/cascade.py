"""Cascading Risk Propagation Engine — Cross-metric impact modeling.

When one metric goes Red, calculates the cascading impact on other metrics
and compliance frameworks. No competitor models interdependencies between
security controls. This gives CISOs real impact visibility.
"""
from typing import Any

import structlog
from fastapi import APIRouter, Request

from grc_dashboard.api.tenant_context import get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import User

logger = structlog.get_logger(__name__)
router = APIRouter()

# Risk dependency graph: metric_id → list of downstream impacts
RISK_DEPENDENCY_GRAPH = {
    "KRI-MTTD-001": {
        "downstream": [
            {
                "metric_id": "KRI-MTTR-001",
                "relationship": "detection_delay_increases_response_time",
                "impact_factor": 0.6,
                "description": "Delayed detection directly increases response time (SOC investigation starts later)",
            },
            {
                "metric_id": "KRI-DLP-001",
                "relationship": "missed_detections_allow_exfiltration",
                "impact_factor": 0.3,
                "description": "Poor detection capability allows data exfiltration to proceed unnoticed",
            },
        ],
        "compliance_impact": [
            {"framework": "DORA", "control": "ICT-2.5", "regulation": "Detection of Anomalous Activities"},
            {"framework": "NIS2", "control": "ART-21.2a", "regulation": "Policies on Risk Analysis"},
            {"framework": "SOC2", "control": "CC7.3", "regulation": "Incident Response"},
        ],
    },
    "KRI-MTTR-001": {
        "downstream": [
            {
                "metric_id": "KRI-DLP-001",
                "relationship": "slow_response_enables_data_loss",
                "impact_factor": 0.5,
                "description": "Slow incident response gives attackers more time to exfiltrate data",
            },
        ],
        "compliance_impact": [
            {"framework": "DORA", "control": "ICT-2.6", "regulation": "Response and Recovery Plans"},
            {"framework": "NIS2", "control": "ART-21.2b", "regulation": "Incident Handling"},
            {"framework": "SOC2", "control": "CC7.3", "regulation": "Incident Response"},
        ],
    },
    "KRI-CVE-001": {
        "downstream": [
            {
                "metric_id": "KRI-MTTD-001",
                "relationship": "unpatched_systems_harder_to_monitor",
                "impact_factor": 0.2,
                "description": "Unpatched vulnerabilities create noise that increases detection difficulty",
            },
            {
                "metric_id": "KRI-MTTR-001",
                "relationship": "exploit_complexity_increases_response_time",
                "impact_factor": 0.35,
                "description": "Active exploitation of unpatched CVEs requires longer, more complex incident response",
            },
        ],
        "compliance_impact": [
            {"framework": "DORA", "control": "ICT-2.2", "regulation": "ICT Asset Management"},
            {"framework": "NIS2", "control": "ART-21.2e", "regulation": "Supply Chain Security"},
            {"framework": "SOC2", "control": "CC7.2", "regulation": "Vulnerability Management"},
        ],
    },
    "KPI-FPR-001": {
        "downstream": [
            {
                "metric_id": "KRI-MTTD-001",
                "relationship": "false_positives_cause_alert_fatigue",
                "impact_factor": 0.4,
                "description": "High false positive rate causes analyst fatigue, slowing genuine threat detection",
            },
            {
                "metric_id": "KRI-MTTR-001",
                "relationship": "wasted_effort_delays_real_incidents",
                "impact_factor": 0.25,
                "description": "SOC analysts waste time investigating false alerts, delaying response to real threats",
            },
        ],
        "compliance_impact": [
            {"framework": "DORA", "control": "ICT-2.5", "regulation": "Detection of Anomalous Activities"},
            {"framework": "SOC2", "control": "CC7.1", "regulation": "System Monitoring"},
        ],
    },
    "KPI-PHI-001": {
        "downstream": [
            {
                "metric_id": "KRI-DLP-001",
                "relationship": "unreviewed_privileges_enable_insider_threats",
                "impact_factor": 0.45,
                "description": "Unreviewed privileged accounts are the #1 vector for insider data theft",
            },
        ],
        "compliance_impact": [
            {"framework": "DORA", "control": "ICT-5.1", "regulation": "Access Control"},
            {"framework": "NIS2", "control": "ART-21.2i", "regulation": "Access Control Policies"},
            {"framework": "SOC2", "control": "CC6.1", "regulation": "Logical Access Controls"},
        ],
    },
    "KRI-DLP-001": {
        "downstream": [],
        "compliance_impact": [
            {"framework": "DORA", "control": "ICT-5.2", "regulation": "Data Leakage Prevention"},
            {"framework": "NIS2", "control": "ART-21.2j", "regulation": "Cryptography"},
            {"framework": "SOC2", "control": "P6.7", "regulation": "Data Loss Prevention"},
        ],
    },
}

# Regulatory fine exposure by framework
REGULATORY_FINES = {
    "DORA": {"max_fine_eur": 10_000_000, "fine_description": "Up to €10M or 5% of annual turnover"},
    "NIS2": {"max_fine_eur": 10_000_000, "fine_description": "Up to €10M or 2% of annual global turnover"},
    "SOC2": {"max_fine_eur": 0, "fine_description": "No direct fine — loss of SOC2 attestation"},
    "GDPR": {"max_fine_eur": 20_000_000, "fine_description": "Up to €20M or 4% of annual global turnover"},
}


@router.get("/analyze")
async def analyze_cascade(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Analyze cascading risk propagation from current Red/Amber metrics."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    metric_map = {m.get("metric_id"): m for m in metrics}

    cascade_chains = []
    total_cascade_var = 0
    affected_frameworks = set()

    # Find all Red and Amber metrics as cascade sources
    risk_sources = [m for m in metrics if m.get("rag_status") in ("Red", "Amber")]

    for source in risk_sources:
        source_id = source.get("metric_id", "")
        dep_info = RISK_DEPENDENCY_GRAPH.get(source_id, {})

        if not dep_info:
            continue

        # Calculate downstream cascade
        downstream_impacts = []
        for downstream in dep_info.get("downstream", []):
            target = metric_map.get(downstream["metric_id"], {})
            impact_factor = downstream["impact_factor"]
            source_var = source.get("var_95_usd", 0)
            cascade_var = int(source_var * impact_factor)
            total_cascade_var += cascade_var

            downstream_impacts.append({
                "target_metric_id": downstream["metric_id"],
                "target_metric_name": target.get("metric_name", downstream["metric_id"]),
                "target_current_rag": target.get("rag_status", "NoData"),
                "relationship": downstream["relationship"],
                "description": downstream["description"],
                "impact_factor": impact_factor,
                "cascaded_var_usd": cascade_var,
            })

        # Compliance framework impact
        compliance_impacts = []
        for comp in dep_info.get("compliance_impact", []):
            affected_frameworks.add(comp["framework"])
            fine_info = REGULATORY_FINES.get(comp["framework"], {})
            compliance_impacts.append({
                **comp,
                "source_rag": source.get("rag_status"),
                "potential_fine": fine_info.get("fine_description", "Unknown"),
                "max_fine_eur": fine_info.get("max_fine_eur", 0),
            })

        cascade_chains.append({
            "source_metric_id": source_id,
            "source_metric_name": source.get("metric_name", source_id),
            "source_rag": source.get("rag_status"),
            "source_var_usd": source.get("var_95_usd", 0),
            "downstream_impacts": downstream_impacts,
            "compliance_impacts": compliance_impacts,
            "total_downstream_var": sum(d["cascaded_var_usd"] for d in downstream_impacts),
        })

    # Calculate total regulatory exposure
    total_regulatory_exposure = sum(
        REGULATORY_FINES.get(fw, {}).get("max_fine_eur", 0)
        for fw in affected_frameworks
    )

    return {
        "cascade_summary": {
            "risk_sources": len(risk_sources),
            "total_cascade_chains": len(cascade_chains),
            "total_cascaded_var_usd": total_cascade_var,
            "affected_frameworks": list(affected_frameworks),
            "total_regulatory_exposure_eur": total_regulatory_exposure,
            "severity": "critical" if total_regulatory_exposure > 5_000_000 else "high" if total_regulatory_exposure > 1_000_000 else "medium",
        },
        "cascade_chains": cascade_chains,
        "dependency_graph": {
            mid: {
                "downstream": [d["metric_id"] for d in info.get("downstream", [])],
                "frameworks": [c["framework"] for c in info.get("compliance_impact", [])],
            }
            for mid, info in RISK_DEPENDENCY_GRAPH.items()
        },
    }


@router.get("/simulate/{metric_id}")
async def simulate_single_cascade(
    metric_id: str,
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Simulate what happens if a specific metric goes Red."""
    results: dict[str, Any] = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    metric_map = {m.get("metric_id"): m for m in metrics}

    source = metric_map.get(metric_id)
    if not source:
        return {"error": f"Metric '{metric_id}' not found"}

    dep_info = RISK_DEPENDENCY_GRAPH.get(metric_id, {})

    # Simulate cascade chain
    visited = set()
    chain = []

    def _trace(mid: str, depth: int = 0) -> None:
        if mid in visited or depth > 5:
            return
        visited.add(mid)
        m = metric_map.get(mid, {})
        deps = RISK_DEPENDENCY_GRAPH.get(mid, {})
        for downstream in deps.get("downstream", []):
            target_id = downstream["metric_id"]
            target = metric_map.get(target_id, {})
            chain.append({
                "depth": depth,
                "from": mid,
                "to": target_id,
                "to_name": target.get("metric_name", target_id),
                "relationship": downstream["description"],
                "impact_factor": downstream["impact_factor"],
            })
            _trace(target_id, depth + 1)

    _trace(metric_id)

    return {
        "source_metric": {
            "metric_id": metric_id,
            "metric_name": source.get("metric_name", metric_id),
            "current_rag": source.get("rag_status"),
            "var_95_usd": source.get("var_95_usd", 0),
        },
        "cascade_chain": chain,
        "total_depth": max((c["depth"] for c in chain), default=0) + 1,
        "affected_metrics": list(visited - {metric_id}),
        "compliance_impacts": dep_info.get("compliance_impact", []),
    }
