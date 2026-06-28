from datetime import datetime

from pydantic import BaseModel, ConfigDict

from grc_dashboard.constants import METRIC_TYPES


class MetricDefinition(BaseModel):
    metric_id: str
    metric_name: str
    metric_type: METRIC_TYPES
    formula: str
    data_source: str
    unit: str
    frequency: str
    business_owner: str
    threshold_config_id: str
    
    # Advanced MNC Features
    regulatory_mappings: list[str] = [] # e.g., ["DORA_ICT_Risk", "NIS2_Art21", "SEC_8K"]
    fair_loss_magnitude_usd: float = 0.0 # Expected cost if this control fails
    fair_threat_event_frequency: float = 0.0 # Annual probability of attack

    model_config = ConfigDict(frozen=True)

class MetricValue(BaseModel):
    metric_id: str
    value: float
    computed_at: datetime
    data_freshness_utc: datetime
    is_stale: bool
    siem_query_hash: str
    computation_formula_hash: str
    threshold_config_hash: str
    
    # Advanced MNC Features
    data_confidence_score: float = 1.0 # 0.0 to 1.0 (Penalized for missing SIEM fields or log drops)
    annualized_loss_expectancy_usd: float = 0.0 # FAIR model computed financial risk
    predictive_breach_days: int | None = None # Days until predicted RAG breach via forecasting

    model_config = ConfigDict(frozen=True)

class MetricSnapshot(BaseModel):
    snapshot_id: str
    generated_at: datetime
    metrics: list[MetricValue]
    dashboard_run_id: str

    model_config = ConfigDict(frozen=True)
