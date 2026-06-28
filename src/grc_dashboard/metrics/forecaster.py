import math

import structlog

from grc_dashboard.models.metric import MetricValue

logger = structlog.get_logger(__name__)

class PredictiveForecaster:
    """
    Advanced MNC feature: Predictive Forecasting.
    Uses Double Exponential Smoothing (Holt's Linear Trend) to project
    when a metric is mathematically destined to breach its 'Red' threshold.
    """
    def __init__(self, alpha: float = 0.3, beta: float = 0.1):
        self.alpha = alpha
        self.beta = beta

    def forecast_breach(self, historical_data: list[MetricValue], red_threshold: float, trend_direction: str) -> int | None:
        """
        Returns the estimated number of days until the metric hits the red threshold.
        Returns None if the metric is trending safely away from the threshold.
        """
        if len(historical_data) < 3:
            return None
            
        values = [m.value for m in sorted(historical_data, key=lambda x: x.computed_at)]
        
        # Initialize Holt's Linear
        level = values[0]
        trend = values[1] - values[0]
        
        for val in values[1:]:
            last_level = level
            level = self.alpha * val + (1 - self.alpha) * (level + trend)
            trend = self.beta * (level - last_level) + (1 - self.beta) * trend
            
        # If trend is 0, we'll never cross
        if abs(trend) < 0.0001:
            return None
            
        # Time to threshold = (Threshold - Current Level) / Trend
        days_to_breach = (red_threshold - level) / trend
        
        # Validate if the breach is mathematically approaching
        if days_to_breach > 0 and days_to_breach <= 90:
            if (trend > 0 and trend_direction == "down") or (trend < 0 and trend_direction == "up"):
                # E.g., MTTD going UP is bad. If trend is positive, it hits the threshold.
                return int(math.ceil(days_to_breach))
                
        return None
