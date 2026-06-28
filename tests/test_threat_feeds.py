"""Tests for threat intel feed normalization and benchmarking loader."""
import pytest

from grc_dashboard.benchmarking.loader import get_industry_benchmarks, load_benchmark_catalog
from grc_dashboard.threat_intel.feeds import _normalize_kev_entries, correlate_threats


def test_normalize_kev_entries():
    raw = [
        {
            "cveID": "CVE-2024-0001",
            "vendorProject": "Acme",
            "product": "Widget",
            "vulnerabilityName": "RCE",
            "dateAdded": "2024-01-01",
            "dueDate": "2024-02-01",
            "knownRansomwareCampaignUse": "Known",
            "notes": "Actively exploited",
        }
    ]
    entries = _normalize_kev_entries(raw)
    assert len(entries) == 1
    assert entries[0]["cve_id"] == "CVE-2024-0001"
    assert entries[0]["known_ransomware_use"] is True


def test_correlate_threats_with_patch_lag():
    kev = [{"cve_id": "CVE-1", "cvss": 9.5, "severity": "CRITICAL"}]
    mitre = []
    metrics = [{"metric_id": "KRI-CVE-001", "value": 10, "rag_status": "Red"}]
    correlations = correlate_threats(kev, mitre, metrics)
    assert any(c["type"] == "kev_exposure" for c in correlations)


def test_benchmark_catalog_loads():
    catalog = load_benchmark_catalog()
    assert catalog["version"]
    assert "Financial Services" in catalog["industries"]
    fs = get_industry_benchmarks("Financial Services")
    assert "KRI-MTTD-001" in fs
    assert "source" in fs["KRI-MTTD-001"]
