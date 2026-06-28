import statistics

import structlog

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import TrendCalculationException
from grc_dashboard.metrics.forecaster import PredictiveForecaster
from grc_dashboard.models.metric import MetricValue
from grc_dashboard.models.rag import TrendDelta

logger = structlog.get_logger(__name__)

class TrendAnalyzer:
    """
    Computes period-over-period trend deltas and identifies statistically
    significant directional shifts (ANCHOR:Q6).
    Now augmented with Predictive Forecasting.
    """
    def __init__(self, period_days: int, config: Settings):
        self.period_days = period_days
        self.config = config
        self.forecaster = PredictiveForecaster()

    def compute_trend(self, current: MetricValue, historical: list[MetricValue]) -> TrendDelta:
        if not historical:
            raise TrendCalculationException(
                message=f"No historical data for metric {current.metric_id}",
                correlation_id="none",
                stage_name="TrendAnalysis",
                dashboard_run_id="none"
            )

        cleaned_history = self._handle_missing_data(historical)
        if not cleaned_history:
             # Returning a flat delta when history is effectively empty
             return TrendDelta(
                 metric_id=current.metric_id,
                 current_value=current.value,
                 previous_value=current.value,
                 delta_percent=0.0,
                 delta_direction="flat",
                 significance=False
             )

        # Naive "previous" is just the mean of the historical window for stability
        previous_val = statistics.mean(m.value for m in cleaned_history)
        
        delta_pct = self._calculate_delta_percent(current.value, previous_val)
        
        direction = "flat"
        if delta_pct > 1.0:
            direction = "up"
        elif delta_pct < -1.0:
            direction = "down"

        is_significant = self._test_significance(current.value, [m.value for m in cleaned_history])
        
        # Determine target direction of the metric (e.g. Coverage wants to go up, MTT/FPR wants to go down)
        target_direction = "down"
        if "COVERAGE" in current.metric_id.upper():
            target_direction = "up"

        breach_days = None
        if len(cleaned_history) >= 3:
            # We assume a red threshold for demo. We'll use 100.0 as mock if no threshold passed.
            breach_days = self.forecaster.forecast_breach(cleaned_history + [current], red_threshold=100.0, trend_direction=target_direction)

        return TrendDelta(
            metric_id=current.metric_id,
            current_value=current.value,
            previous_value=previous_val,
            delta_percent=delta_pct,
            delta_direction=direction, # type: ignore
            significance=is_significant,
            predictive_breach_days=breach_days
        )

    def _calculate_delta_percent(self, current: float, previous: float) -> float:
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return ((current - previous) / previous) * 100.0

    def _test_significance(self, current: float, historical_values: list[float]) -> bool:
        if len(historical_values) < 2:
            return False
            
        std_dev = statistics.stdev(historical_values)
        mean_val = statistics.mean(historical_values)
        
        # If the delta exceeds 1 standard deviation, flag as significant
        return abs(current - mean_val) > std_dev

    def _handle_missing_data(self, historical: list[MetricValue]) -> list[MetricValue]:
        # Filter out missing/stale values
        return [m for m in historical if not m.is_stale]
