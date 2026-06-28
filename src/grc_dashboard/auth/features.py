"""Feature-based access control for VALENCE modules."""
from __future__ import annotations

from typing import Any

ALL_FEATURES: tuple[str, ...] = (
    "dashboard",
    "risk",
    "whatif",
    "benchmarking",
    "threat_intel",
    "compliance",
    "timeline",
    "evidence",
    "findings",
    "reports",
    "connectors",
    "team_admin",
    "policies",
    "auditor_portal",
    "personnel",
    "questionnaires",
    "training",
    "pentest",
    "vendors",
    "mobile",
    "control_monitoring",
    "remediation",
    "trust_center",
    "platform",
    "enterprise",
    "itsm",
    "auditor_marketplace",
)

FEATURE_LABELS: dict[str, str] = {
    "dashboard": "Security Dashboard",
    "risk": "Risk Analysis",
    "whatif": "Risk Simulator",
    "benchmarking": "Industry Benchmarking",
    "threat_intel": "Threat Intelligence",
    "compliance": "Compliance Frameworks",
    "timeline": "Audit Timeline",
    "evidence": "Evidence Vault",
    "findings": "Audit Findings",
    "reports": "Reports & Board Deck",
    "connectors": "SIEM Connectors",
    "team_admin": "Team Access Management",
    "policies": "Policy Library & Attestation",
    "auditor_portal": "Auditor Portal",
    "personnel": "Personnel & Device Compliance",
    "questionnaires": "Security Questionnaires",
    "training": "Security Awareness Training",
    "pentest": "Penetration Test Management",
    "vendors": "Vendor & Third-Party Risk (SENTINEL)",
    "mobile": "Executive Mobile Snapshot",
    "control_monitoring": "Continuous Control Monitoring",
    "remediation": "Remediation Task Workflow",
    "trust_center": "Public Trust Center",
    "platform": "Platform & Competitive Overview",
    "enterprise": "Enterprise Workflows & Business Units",
    "itsm": "ITSM Sync & CMDB",
    "auditor_marketplace": "Auditor Firm Marketplace",
}

DEPARTMENTS: tuple[str, ...] = ("grc", "soc", "ir", "general")

DEPARTMENT_LABELS: dict[str, str] = {
    "grc": "GRC / Compliance",
    "soc": "SOC / Detection",
    "ir": "Incident Response",
    "general": "General / Custom",
}

DEPARTMENT_PRESETS: dict[str, list[str]] = {
    "grc": ["dashboard", "compliance", "timeline", "evidence", "findings", "reports", "benchmarking", "policies", "auditor_portal", "personnel", "questionnaires", "training", "pentest", "vendors", "mobile", "control_monitoring", "remediation", "trust_center", "platform", "enterprise", "itsm", "auditor_marketplace"],
    "soc": ["dashboard", "risk", "threat_intel", "connectors", "findings", "timeline"],
    "ir": ["dashboard", "risk", "threat_intel", "timeline", "findings", "connectors"],
}

ROLE_FEATURE_DEFAULTS: dict[str, list[str]] = {
    "admin": list(ALL_FEATURES),
    "ciso": [f for f in ALL_FEATURES if f != "team_admin"],
    "analyst": [
        "dashboard", "risk", "whatif", "threat_intel", "connectors", "findings", "timeline",
    ],
    "auditor": [
        "dashboard", "compliance", "timeline", "evidence", "findings", "reports", "benchmarking",
        "policies", "auditor_portal", "questionnaires", "training",
    ],
}


def resolve_features(
    role: str,
    department: str,
    feature_permissions: dict[str, Any] | list[str] | None,
) -> dict[str, bool]:
    """Return feature map for a user. Explicit permissions override presets."""
    if isinstance(feature_permissions, list):
        allowed = set(feature_permissions)
        return {f: f in allowed for f in ALL_FEATURES}

    if isinstance(feature_permissions, dict) and feature_permissions:
        return {f: bool(feature_permissions.get(f, False)) for f in ALL_FEATURES}

    if department in DEPARTMENT_PRESETS:
        allowed = set(DEPARTMENT_PRESETS[department])
        if role == "admin":
            allowed.add("team_admin")
        return {f: f in allowed for f in ALL_FEATURES}

    allowed = set(ROLE_FEATURE_DEFAULTS.get(role, ROLE_FEATURE_DEFAULTS["analyst"]))
    return {f: f in allowed for f in ALL_FEATURES}


def allowed_feature_list(
    role: str,
    department: str,
    feature_permissions: dict[str, Any] | list[str] | None,
) -> list[str]:
    features = resolve_features(role, department, feature_permissions)
    return [f for f, ok in features.items() if ok]


def has_feature(
    role: str,
    department: str,
    feature_permissions: dict[str, Any] | list[str] | None,
    feature: str,
) -> bool:
    return resolve_features(role, department, feature_permissions).get(feature, False)
