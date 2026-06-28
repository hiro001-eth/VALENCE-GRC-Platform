from pathlib import Path

import structlog

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import FPRFormulaException
from grc_dashboard.models.siem import SIEMEvent

logger = structlog.get_logger(__name__)

class FPRCalculator:
    """
    Immutable False Positive Rate calculator. Enforces a consistent
    denominator that strictly excludes unclassified alerts (ANCHOR:I6).
    """
    def __init__(self, formula_path: Path, config: Settings):
        self.formula_path = formula_path
        self.config = config
        # Ideally, we load and freeze the formula YAML here.
        # For boilerplate, we hardcode the structural constraint rule.
        self.true_positive_labels = {"true_positive", "tp", "confirmed_incident"}
        self.false_positive_labels = {"false_positive", "fp", "benign", "test"}

    def calculate(self, events: list[SIEMEvent]) -> float:
        classified = self._filter_classified_events(events)
        fp_count = self._count_false_positives(classified)
        tp_count = self._count_true_positives(classified)
        
        self._validate_denominator(fp_count, tp_count)
        
        if (fp_count + tp_count) == 0:
            return 0.0
            
        return (fp_count / (fp_count + tp_count)) * 100.0

    def _filter_classified_events(self, events: list[SIEMEvent]) -> list[SIEMEvent]:
        # Excludes all unclassified alerts (where classification_label is None or Unknown)
        valid_labels = self.true_positive_labels | self.false_positive_labels
        return [
            e for e in events 
            if e.raw_fields.get("classification_label", "").lower() in valid_labels
        ]

    def _count_false_positives(self, events: list[SIEMEvent]) -> int:
        return sum(1 for e in events if e.raw_fields.get("classification_label", "").lower() in self.false_positive_labels)

    def _count_true_positives(self, events: list[SIEMEvent]) -> int:
        return sum(1 for e in events if e.raw_fields.get("classification_label", "").lower() in self.true_positive_labels)

    def _validate_denominator(self, fp: int, tp: int) -> None:
        if fp < 0 or tp < 0:
            raise FPRFormulaException(
                message="FPR denominator inputs cannot be negative.",
                correlation_id="none",
                stage_name="MetricComputation",
                dashboard_run_id="none"
            )
