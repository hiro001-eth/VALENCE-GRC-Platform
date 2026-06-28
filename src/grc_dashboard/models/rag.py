from typing import Literal

from pydantic import BaseModel, ConfigDict


class RAGThreshold(BaseModel):
    threshold_id: str
    metric_id: str
    green_min: float
    green_max: float
    amber_min: float
    amber_max: float
    red_min: float
    red_max: float
    inclusive_exclusive: Literal["[min, max)", "(min, max]", "[min, max]"]

    model_config = ConfigDict(frozen=True)

class RAGAssignment(BaseModel):
    metric_id: str
    value: float
    rag_status: str
    threshold_config_hash: str
    boundary_flag: bool
    
    # Advanced MNC Features
    annualized_loss_expectancy_usd: float = 0.0
    var_95_usd: float = 0.0
    probability_of_breach: float = 0.0

    model_config = ConfigDict(frozen=True)

class TrendDelta(BaseModel):
    metric_id: str
    current_value: float
    previous_value: float
    delta_percent: float
    delta_direction: Literal["up", "down", "flat"]
    significance: bool
    
    # Advanced MNC Features
    predictive_breach_days: int | None = None

    model_config = ConfigDict(frozen=True)
