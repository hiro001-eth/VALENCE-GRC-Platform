from decimal import Decimal

import structlog

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import RAGAssignmentException, ThresholdFrozenException
from grc_dashboard.metrics.fair_engine import FAIREngine
from grc_dashboard.models.metric import MetricDefinition, MetricValue
from grc_dashboard.models.rag import RAGAssignment, RAGThreshold

logger = structlog.get_logger(__name__)

class ClassificationEngine:
    """
    Deterministic RAG classification engine (ANCHOR:I3).
    Assigns Red/Amber/Green status via immutable ThresholdConfig.
    Now enhanced with FAIR Risk Quantification for MNC boards.
    """
    def __init__(self, thresholds: list[RAGThreshold], definitions: list[MetricDefinition], config: Settings):
        # Defensively ensure threshold mappings are frozen and indexed
        self.thresholds = {t.metric_id: t for t in thresholds}
        self.definitions = {d.metric_id: d for d in definitions}
        self.fair_engine = FAIREngine()
        self.config = config
        self._validate_threshold_frozen()

    def classify(self, metric: MetricValue) -> RAGAssignment:
        """Evaluates a single metric against its immutable threshold boundaries."""
        if metric.metric_id not in self.thresholds:
            raise RAGAssignmentException(
                message=f"No threshold configuration found for {metric.metric_id}",
                correlation_id="none",
                stage_name="Classification",
                dashboard_run_id="none"
            )

        threshold = self.thresholds[metric.metric_id]
        
        # If the data is stale, override RAG status entirely (ANCHOR:I1)
        if metric.is_stale:
            return RAGAssignment(
                metric_id=metric.metric_id,
                value=metric.value,
                rag_status="Stale",
                threshold_config_hash=metric.threshold_config_hash,
                boundary_flag=False
            )

        status = self._apply_boundary_semantics(metric.value, threshold)
        is_boundary = self._flag_boundary_cases(metric.value, threshold)
        
        definition = self.definitions.get(metric.metric_id)
        ale_usd = 0.0
        var_95_usd = 0.0
        prob_breach = 0.0
        if definition:
            sim_res = self.fair_engine.simulate_risk(definition, metric.value, status)
            ale_usd = sim_res["average_exposure"]
            var_95_usd = sim_res["var_95"]
            prob_breach = sim_res["probability_of_breach"]

        return RAGAssignment(
            metric_id=metric.metric_id,
            value=metric.value,
            rag_status=status,
            threshold_config_hash=metric.threshold_config_hash,
            boundary_flag=is_boundary,
            annualized_loss_expectancy_usd=ale_usd,
            var_95_usd=var_95_usd,
            probability_of_breach=prob_breach
        )

    def _apply_boundary_semantics(self, value: float, threshold: RAGThreshold) -> str:
        v = Decimal(str(value))
        
        # Enforce inclusive/exclusive semantics
        if threshold.inclusive_exclusive == "[min, max)":
            if Decimal(str(threshold.green_min)) <= v < Decimal(str(threshold.green_max)):
                return "Green"
            if Decimal(str(threshold.amber_min)) <= v < Decimal(str(threshold.amber_max)):
                return "Amber"
            if v >= Decimal(str(threshold.red_min)):
                return "Red"
        
        elif threshold.inclusive_exclusive == "(min, max]":
            if Decimal(str(threshold.green_min)) < v <= Decimal(str(threshold.green_max)):
                return "Green"
            if Decimal(str(threshold.amber_min)) < v <= Decimal(str(threshold.amber_max)):
                return "Amber"
            if v <= Decimal(str(threshold.red_max)):
                return "Red"

        # Fallback if outside strict domains but still requires evaluation
        return "Amber"

    def _flag_boundary_cases(self, value: float, threshold: RAGThreshold) -> bool:
        """Flags metrics sitting exactly on boundary edges for audit highlighting."""
        v = value
        edges = [
            threshold.green_min, threshold.green_max, 
            threshold.amber_min, threshold.amber_max, 
            threshold.red_min, threshold.red_max
        ]
        return any(abs(v - edge) < 0.0001 for edge in edges)

    def _validate_threshold_frozen(self) -> None:
        """Enforces Pydantic frozen model constraints to prevent runtime overrides."""
        # By iterating and asserting the Pydantic model is frozen, we satisfy ANCHOR:I3 L2
        for t in self.thresholds.values():
            if not t.model_config.get("frozen", False):
                raise ThresholdFrozenException(
                    message=f"Threshold {t.threshold_id} is mutable! Determinism violated.",
                    correlation_id="none",
                    stage_name="Classification",
                    dashboard_run_id="none"
                )
