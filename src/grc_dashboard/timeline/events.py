"""Timeline events — demo-only narrative; production orgs get real events only."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def demo_security_events() -> list[dict[str, Any]]:
    """Curated storyline for sandbox evaluation tenants only."""
    now = datetime.now(UTC)
    return [
        {
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "type": "incident",
            "severity": "high",
            "title": "Ransomware attempt detected and blocked",
            "description": "CryptoLocker variant blocked by EDR. MTTR spiked during investigation.",
            "affected_metrics": ["KRI-MTTR-001", "KRI-MTTD-001"],
        },
        {
            "timestamp": (now - timedelta(days=8)).isoformat(),
            "type": "deployment",
            "severity": "info",
            "title": "SOAR playbook v2.3 deployed",
            "description": "Updated incident response automation. Expected 15% MTTR improvement.",
            "affected_metrics": ["KRI-MTTR-001"],
        },
        {
            "timestamp": (now - timedelta(days=15)).isoformat(),
            "type": "vulnerability",
            "severity": "critical",
            "title": "CVE-2025-21298 (OLE RCE) — CISA KEV listed",
            "description": "Critical Windows vulnerability added to CISA KEV. 3 systems affected.",
            "affected_metrics": ["KRI-CVE-001"],
        },
        {
            "timestamp": (now - timedelta(days=22)).isoformat(),
            "type": "compliance",
            "severity": "warning",
            "title": "DORA ICT-2.6 compliance gap identified",
            "description": "Response time exceeded DORA threshold. Remediation plan initiated.",
            "affected_metrics": ["KRI-MTTR-001"],
        },
        {
            "timestamp": (now - timedelta(days=35)).isoformat(),
            "type": "improvement",
            "severity": "info",
            "title": "ML detection model retrained",
            "description": "False positive rate reduced from 28% to 18.4% after model update.",
            "affected_metrics": ["KPI-FPR-001"],
        },
        {
            "timestamp": (now - timedelta(days=45)).isoformat(),
            "type": "incident",
            "severity": "critical",
            "title": "Phishing campaign targeting finance team",
            "description": "Coordinated spear-phishing detected. 12 emails blocked, 2 reached inbox.",
            "affected_metrics": ["KRI-MTTD-001", "KRI-DLP-001"],
        },
        {
            "timestamp": (now - timedelta(days=60)).isoformat(),
            "type": "audit",
            "severity": "info",
            "title": "SOC2 Type II audit period started",
            "description": "External auditors began continuous monitoring review period.",
            "affected_metrics": [],
        },
    ]
