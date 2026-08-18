from typing import Any

import structlog

from grc_dashboard.compliance.framework_loader import FrameworkLoader

logger = structlog.get_logger(__name__)


class ComplianceGapAnalyzer:
    """Computes exact compliance controls status and maps coverage gaps."""

    def __init__(self, loader: FrameworkLoader | None = None) -> None:
        self.loader = loader or FrameworkLoader()

    def analyze_gap(self, framework_name: str, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        rule = self.loader.load_framework(framework_name)
        if not rule:
            return {
                "framework": framework_name,
                "coverage_pct": 0.0,
                "readiness_pct": 0.0,
                "compliant": 0,
                "at_risk": 0,
                "non_compliant": 0,
                "controls": [],
                "gaps": ["Framework rule configuration file missing."]
            }

        metric_rag = {m.get("metric_id"): m.get("rag_status", "NoData") for m in metrics}

        controls_detail = []
        compliant_count = 0
        at_risk_count = 0
        non_compliant_count = 0
        gaps = []

        for control in rule.controls:
            linked_rags = [metric_rag.get(mid, "NoData") for mid in control.metric_ids]

            if not linked_rags or all(r == "NoData" for r in linked_rags):
                status = "No Data"
                gaps.append(f"Control {control.id} ({control.title}): No security metrics linked.")
            elif all(r == "Green" for r in linked_rags):
                status = "Compliant"
                compliant_count += 1
            elif any(r == "Red" for r in linked_rags):
                status = "Non-Compliant"
                non_compliant_count += 1
                gaps.append(f"Control {control.id} ({control.title}): Critical breach in linked metrics.")
            elif any(r == "Amber" for r in linked_rags):
                status = "At Risk"
                at_risk_count += 1
                gaps.append(f"Control {control.id} ({control.title}): Approaching threshold SLA limit.")
            else:
                status = "No Data"

            controls_detail.append({
                "control_id": control.id,
                "title": control.title,
                "description": control.description,
                "metric_ids": control.metric_ids,
                "status": status,
                "linked_metric_rags": dict(zip(control.metric_ids, linked_rags)),
            })

        total = len(rule.controls)
        coverage_pct = round((compliant_count / total) * 100, 1) if total > 0 else 0.0
        # Weighted readiness: compliant=100%, at-risk=50%, non-compliant/no-data=0%
        scored = compliant_count + (0.5 * at_risk_count)
        readiness_pct = round((scored / total) * 100, 1) if total > 0 else 0.0

        return {
            "framework": framework_name,
            "full_name": rule.full_name,
            "version": rule.version,
            "total_controls": total,
            "compliant": compliant_count,
            "at_risk": at_risk_count,
            "non_compliant": non_compliant_count,
            "coverage_pct": coverage_pct,
            "readiness_pct": readiness_pct,
            "controls": controls_detail,
            "gaps": gaps,
        }

    def aggregate_readiness(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        """Cross-framework compliance readiness for executive dashboard."""
        frameworks = self.loader.list_frameworks()
        breakdown: list[dict[str, Any]] = []
        total_controls = 0
        weighted_sum = 0.0

        for fw in frameworks:
            analysis = self.analyze_gap(fw, metrics)
            count = analysis.get("total_controls", 0)
            readiness = analysis.get("readiness_pct", 0.0)
            total_controls += count
            weighted_sum += readiness * count
            breakdown.append({
                "framework": fw,
                "full_name": analysis.get("full_name", fw),
                "readiness_pct": readiness,
                "coverage_pct": analysis.get("coverage_pct", 0.0),
                "compliant": analysis.get("compliant", 0),
                "at_risk": analysis.get("at_risk", 0),
                "non_compliant": analysis.get("non_compliant", 0),
                "total_controls": count,
            })

        overall = round(weighted_sum / total_controls, 1) if total_controls else 0.0
        return {
            "readiness_pct": overall,
            "frameworks": breakdown,
            "total_controls": total_controls,
        }
