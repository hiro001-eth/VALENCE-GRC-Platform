from pathlib import Path
from typing import Any

import structlog

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import CoverageMappingException
from grc_dashboard.mitre.stix_loader import STIXLoader
from grc_dashboard.models.mitre import CoverageMatrix, DetectionRuleMapping, TechniqueCoverage

logger = structlog.get_logger(__name__)

class CoverageMapper:
    """
    Detection rule to MITRE ATT&CK technique mapping engine (ANCHOR:Q7).
    Computes per-technique coverage scores based on weighted rule confidence.
    """
    def __init__(self, mapping_path: Path, stix_loader: STIXLoader, config: Settings):
        self.mapping_path = mapping_path
        self.stix_loader = stix_loader
        self.config = config

    async def map_coverage(self, detection_rules: list[DetectionRuleMapping]) -> CoverageMatrix:
        try:
            stix_bundle = await self.stix_loader.load_enterprise_matrix()
            techniques_meta = self._extract_techniques_from_stix(stix_bundle)
            
            # Group rules by technique ID
            rules_by_technique: dict[str, list[DetectionRuleMapping]] = {}
            for rule in detection_rules:
                for t_id in rule.technique_ids:
                    if t_id not in rules_by_technique:
                        rules_by_technique[t_id] = []
                    rules_by_technique[t_id].append(rule)

            coverages = []
            tactics_set = set()

            for tech_id, meta in techniques_meta.items():
                rules = rules_by_technique.get(tech_id, [])
                score = self._compute_technique_score(tech_id, rules)
                mapped_rule_names = [r.rule_name for r in rules]
                is_gap = score < 0.5
                
                tactic = meta.get("tactic", "Unknown")
                tactics_set.add(tactic)
                
                coverages.append(TechniqueCoverage(
                    technique_id=tech_id,
                    technique_name=meta.get("name", "Unknown"),
                    tactic=tactic,
                    coverage_score=score,
                    mapped_rules=mapped_rule_names,
                    gap_flag=is_gap
                ))

            overall = self._compute_overall_coverage(coverages)
            gaps = self._identify_gaps(coverages)

            return CoverageMatrix(
                tactics=sorted(list(tactics_set)),
                techniques=coverages,
                overall_coverage=overall,
                gap_count=len(gaps),
                matrix_hash="static_hash_placeholder" # Would use hash_utils in production
            )

        except Exception as e:
            raise CoverageMappingException(
                message=f"Failed to map coverage: {e}",
                correlation_id="none",
                stage_name="MITRECoverage",
                dashboard_run_id="none"
            ) from e

    def _extract_techniques_from_stix(self, bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
        techniques = {}
        for obj in bundle.get("objects", []):
            if obj.get("type") == "attack-pattern":
                ext_refs = obj.get("external_references", [])
                t_id = next((ref["external_id"] for ref in ext_refs if ref.get("source_name") == "mitre-attack"), None)
                if t_id:
                    kill_chains = obj.get("kill_chain_phases", [])
                    tactic = kill_chains[0].get("phase_name", "unknown") if kill_chains else "unknown"
                    techniques[t_id] = {"name": obj.get("name", t_id), "tactic": tactic}
        return techniques

    def _compute_technique_score(self, technique_id: str, rules: list[DetectionRuleMapping]) -> float:
        if not rules:
            return 0.0
        # Score = min(1.0, sum(confidence))
        score = sum(r.confidence for r in rules)
        return min(1.0, score)

    def _identify_gaps(self, coverages: list[TechniqueCoverage]) -> list[TechniqueCoverage]:
        return [c for c in coverages if c.gap_flag]

    def _compute_overall_coverage(self, coverages: list[TechniqueCoverage]) -> float:
        if not coverages:
            return 0.0
        return sum(c.coverage_score for c in coverages) / len(coverages)
