"""Versioned industry benchmark loader with full data provenance."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_BENCHMARK_PATH = Path("rules/industry_benchmarks.yaml")

LOWER_IS_BETTER = {
    "KRI-MTTD-001": True,
    "KRI-MTTR-001": True,
    "KPI-FPR-001": True,
    "KRI-CVE-001": True,
    "KPI-PHI-001": False,
    "KRI-DLP-001": True,
}


@lru_cache(maxsize=1)
def load_benchmark_catalog() -> dict[str, Any]:
    if not _BENCHMARK_PATH.exists():
        return {"version": "unknown", "last_updated": "", "methodology": "", "industries": {}}
    with open(_BENCHMARK_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "version": data.get("version", ""),
        "last_updated": data.get("last_updated", ""),
        "methodology": (data.get("methodology") or "").strip(),
        "industries": data.get("industries", {}),
    }


def get_industry_benchmarks(industry: str) -> dict[str, dict[str, Any]]:
    catalog = load_benchmark_catalog()
    industries = catalog["industries"]
    return industries.get(industry, industries.get("Financial Services", {}))


def calculate_percentile(value: float, benchmarks: dict[str, Any], lower_is_better: bool) -> int:
    p25, p50, p75, p90 = benchmarks["p25"], benchmarks["p50"], benchmarks["p75"], benchmarks["p90"]
    if lower_is_better:
        if value <= p25:
            return min(99, int(75 + 24 * (p25 - value) / max(1, p25)))
        if value <= p50:
            return int(50 + 25 * (p50 - value) / max(1, p50 - p25))
        if value <= p75:
            return int(25 + 25 * (p75 - value) / max(1, p75 - p50))
        if value <= p90:
            return int(10 + 15 * (p90 - value) / max(1, p90 - p75))
        return max(1, int(10 * (1 - (value - p90) / max(1, p90))))
    if value >= p90:
        return min(99, int(90 + 9 * (value - p90) / max(1, 100 - p90)))
    if value >= p75:
        return int(75 + 15 * (value - p75) / max(1, p90 - p75))
    if value >= p50:
        return int(50 + 25 * (value - p50) / max(1, p75 - p50))
    if value >= p25:
        return int(25 + 25 * (value - p25) / max(1, p50 - p25))
    return max(1, int(25 * value / max(1, p25)))
