import structlog
from pydantic import BaseModel, ConfigDict

from grc_dashboard.models.metric import MetricDefinition

logger = structlog.get_logger(__name__)

class ComplianceFramework(BaseModel):
    framework_name: str
    version: str
    controls_mapped: int
    coverage_percent: float
    
    model_config = ConfigDict(frozen=True)

class RegulatoryMapper:
    """
    Advanced MNC feature: Regulatory Mapping.
    Maps operational metrics to regulatory compliance frameworks (DORA, NIS2, SEC).
    This allows the dashboard to generate a "Compliance Readiness Matrix".
    """
    def __init__(self) -> None:
        # In a real environment, this would be loaded from a YAML mapping file
        self.frameworks = {
            "DORA_ICT_Risk": {"total_controls": 45},
            "NIS2_Art21": {"total_controls": 30},
            "SEC_8K": {"total_controls": 10}
        }
        
    def map_metrics_to_frameworks(self, metric_definitions: list[MetricDefinition]) -> list[ComplianceFramework]:
        """
        Calculates compliance coverage based on mapped metrics.
        """
        control_counts = {k: 0 for k in self.frameworks}
        
        for d in metric_definitions:
            for mapping in d.regulatory_mappings:
                if mapping in control_counts:
                    control_counts[mapping] += 1
                    
        results = []
        for fw, stats in self.frameworks.items():
            mapped = control_counts.get(fw, 0)
            total = stats["total_controls"]
            coverage = (mapped / total) * 100.0 if total > 0 else 0.0
            
            results.append(ComplianceFramework(
                framework_name=fw,
                version="Latest",
                controls_mapped=mapped,
                coverage_percent=round(coverage, 2)
            ))
            
        return results
