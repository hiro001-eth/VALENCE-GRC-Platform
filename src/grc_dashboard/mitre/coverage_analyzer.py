from collections import defaultdict
from typing import Any

import structlog

from grc_dashboard.config import Settings
from grc_dashboard.models.mitre import CoverageMatrix, TechniqueCoverage

logger = structlog.get_logger(__name__)

class CoverageAnalyzer:
    """
    Coverage matrix analysis and heatmap data generation (ANCHOR:Q8).
    Prepares layout schemas for the DashboardRenderer.
    """
    def __init__(self, config: Settings):
        self.config = config

    def analyze_gaps(self, matrix: CoverageMatrix) -> list[dict[str, Any]]:
        gaps = [t for t in matrix.techniques if t.gap_flag]
        prioritized = self._prioritize_gaps(gaps)
        
        reports = []
        for gap in prioritized:
            reports.append({
                "technique_id": gap.technique_id,
                "technique_name": gap.technique_name,
                "tactic": gap.tactic,
                "score": gap.coverage_score,
                "recommendations": self._generate_recommendations(gap)
            })
        return reports

    def _prioritize_gaps(self, gaps: list[TechniqueCoverage]) -> list[TechniqueCoverage]:
        # Sort by tactic logical flow (Initial Access -> Impact), then by lowest score
        # For boilerplate, just sort by score ascending
        return sorted(gaps, key=lambda x: x.coverage_score)

    def _generate_recommendations(self, gap: TechniqueCoverage) -> list[str]:
        return [
            f"Develop minimum 1 Sigma rule mapped to {gap.technique_id}",
            "Review compensating endpoint controls",
            "Assess log source availability for technique validation"
        ]

    def _build_heatmap_data(self, matrix: CoverageMatrix) -> dict[str, Any]:
        """
        Transforms the flat matrix into a nested layout for Plotly heatmaps.
        Groups techniques by tactic columns.
        """
        grouped = defaultdict(list)
        for tech in matrix.techniques:
            grouped[tech.tactic].append({
                "id": tech.technique_id,
                "name": tech.technique_name,
                "score": tech.coverage_score,
                "rules": len(tech.mapped_rules)
            })
            
        return dict(grouped)
