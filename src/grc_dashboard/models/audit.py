from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from grc_dashboard.constants import LogEventType


class DashboardRunMetadata(BaseModel):
    run_id: str
    start_time: datetime
    end_time: datetime | None = None
    pipeline_version: str
    python_version: str
    dependency_lockfile_hash: str
    threshold_config_hash: str
    metric_config_hash: str
    total_metrics_computed: int = 0
    total_rag_assigned: int = 0
    stale_metric_count: int = 0
    siem_queries_executed: int = 0
    coverage_gap_count: int = 0

    model_config = ConfigDict(frozen=True)

class AuditLogEntry(BaseModel):
    timestamp_utc: datetime
    correlation_id: str
    dashboard_run_id: str
    stage_name: str
    event_type: LogEventType
    log_severity: Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
    message: str
    metric_id: str | None = None
    metric_value: float | None = None
    rag_status: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

class HealthCheckResult(BaseModel):
    check_name: str
    passed: bool
    details: str
    severity: Literal["INFO", "WARN", "FATAL"]

    model_config = ConfigDict(frozen=True)
