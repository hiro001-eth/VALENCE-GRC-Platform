from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from grc_dashboard.models.rag import TrendDelta


class DashboardCard(BaseModel):
    metric_id: str
    title: str
    value: str
    rag_status: str
    trend_delta: TrendDelta | None = None
    chart_data: list[dict[str, Any]] = []
    
    # Tier-0 Advanced Features
    executive_narrative: str = ""
    itsm_ticket_id: str | None = None
    financial_exposure_usd: float = 0.0
    var_95_usd: float = 0.0
    probability_of_breach: float = 0.0

    model_config = ConfigDict(frozen=True)

class DashboardArtifact(BaseModel):
    artifact_id: str
    html_path: Path
    pdf_path: Path
    generated_at: datetime
    metric_snapshot_hash: str
    dashboard_run_id: str

    model_config = ConfigDict(frozen=True)

class PDFMetadata(BaseModel):
    dashboard_run_id: str
    generated_at: datetime
    metric_snapshot_hash: str
    threshold_config_hash: str
    siem_query_hashes: list[str]

    model_config = ConfigDict(frozen=True)
