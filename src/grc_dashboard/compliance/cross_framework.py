"""Cross-framework control mapping (SCF-style unified controls)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CACHE: list[dict[str, Any]] | None = None


def load_cross_framework_map() -> list[dict[str, Any]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = Path(__file__).resolve().parents[3] / "rules" / "cross_framework_map.yaml"
    if not path.exists():
        _CACHE = []
        return _CACHE
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    _CACHE = data.get("unified_controls", [])
    return _CACHE


def build_cross_framework_view(gap_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Map per-framework gap analysis into unified control coverage."""
    unified = load_cross_framework_map()
    if not unified:
        return []

    views: list[dict[str, Any]] = []
    for uc in unified:
        uid = uc.get("id", "")
        frameworks = uc.get("frameworks", {})
        statuses: list[str] = []
        for fw_key, control_id in frameworks.items():
            fw_analysis = gap_results.get(fw_key, {})
            controls = {c["control_id"]: c for c in fw_analysis.get("controls", [])}
            ctrl = controls.get(control_id)
            if ctrl:
                statuses.append(ctrl.get("status", "No Data"))
        if not statuses:
            overall = "No Data"
        elif all(s == "Compliant" for s in statuses):
            overall = "Compliant"
        elif any(s == "Non-Compliant" for s in statuses):
            overall = "Non-Compliant"
        elif any(s == "At Risk" for s in statuses):
            overall = "At Risk"
        else:
            overall = "No Data"
        views.append({
            "unified_id": uid,
            "title": uc.get("title", uid),
            "overall_status": overall,
            "framework_mappings": frameworks,
            "framework_statuses": dict(zip(frameworks.keys(), statuses, strict=False)),
        })
    return views
