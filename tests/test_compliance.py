from pathlib import Path

import pytest

from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer


def test_framework_loader_lists_and_loads():
    loader = FrameworkLoader()
    frameworks = loader.list_frameworks()
    
    assert "DORA" in frameworks
    assert "NIS2" in frameworks
    assert "SOC2" in frameworks

    dora_rule = loader.load_framework("DORA")
    assert dora_rule is not None
    assert dora_rule.framework_name == "DORA"
    assert len(dora_rule.controls) > 0


def test_gap_analyzer_computes_status():
    loader = FrameworkLoader()
    analyzer = ComplianceGapAnalyzer(loader)

    # Test metrics with mixed compliance statuses
    test_metrics = [
        {"metric_id": "KRI-MTTD-001", "rag_status": "Green"},
        {"metric_id": "KRI-MTTR-001", "rag_status": "Amber"},
        {"metric_id": "KRI-CVE-001", "rag_status": "Green"},
        {"metric_id": "KPI-FPR-001", "rag_status": "Green"},
        {"metric_id": "KPI-PHI-001", "rag_status": "Green"},
        {"metric_id": "KRI-DLP-001", "rag_status": "Red"},
    ]

    analysis = analyzer.analyze_gap("DORA", test_metrics)
    assert analysis["framework"] == "DORA"
    assert analysis["total_controls"] == 6

    # 1 check: CC-2.1 linked to MTTD (Green) + MTTR (Amber) -> At Risk
    # 2 check: CC-2.2 linked to CVE (Green) -> Compliant
    # 3 check: CC-5.2 linked to DLP (Red) -> Non-Compliant

    control_map = {c["control_id"]: c for c in analysis["controls"]}
    assert control_map["DORA-ICT-2.1"]["status"] == "At Risk"
    assert control_map["DORA-ICT-2.2"]["status"] == "Compliant"
    assert control_map["DORA-ICT-5.2"]["status"] == "Non-Compliant"

    assert len(analysis["gaps"]) > 0
    assert any("DORA-ICT-5.2" in g for g in analysis["gaps"])
