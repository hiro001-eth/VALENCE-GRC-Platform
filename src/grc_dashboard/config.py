import functools
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = ".env"


class SIEMSettings(BaseSettings):
    siem_type: Literal["Splunk", "Elastic", "QRadar"] = "Elastic"
    base_url: AnyHttpUrl
    api_key: SecretStr
    data_ttl_minutes: int = 30
    max_results_per_page: int = 10000
    query_timeout_seconds: int = 300
    
    model_config = SettingsConfigDict(env_prefix="SIEM_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


class MetricSettings(BaseSettings):
    metric_config_path: Path = Path("rules/metric_definitions.yaml")
    threshold_config_path: Path = Path("rules/threshold_config.yaml")
    fpr_formula_path: Path = Path("rules/fpr_formula.yaml")
    trend_period_days: int = 7
    
    model_config = SettingsConfigDict(env_prefix="METRIC_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


class MITRESettings(BaseSettings):
    stix_url: AnyHttpUrl
    cache_ttl_hours: int = 168
    detection_mapping_path: Path = Path("rules/detection_mapping.yaml")
    
    model_config = SettingsConfigDict(env_prefix="MITRE_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


class DashboardSettings(BaseSettings):
    title: str = "Security Metrics Dashboard"
    refresh_interval_seconds: int = 300
    pdf_output_dir: Path = Path("output/")
    
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


class PipelineSettings(BaseSettings):
    log_level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = "INFO"
    run_id_prefix: str = "VALENCE"
    output_dir: Path = Path("output/")
    
    model_config = SettingsConfigDict(env_prefix="PIPELINE_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


class Settings(BaseSettings):
    siem: SIEMSettings = SIEMSettings()  # type: ignore
    metric: MetricSettings = MetricSettings()
    mitre: MITRESettings = MITRESettings()  # type: ignore
    dashboard: DashboardSettings = DashboardSettings()
    pipeline: PipelineSettings = PipelineSettings()
    
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


@functools.lru_cache
def get_settings() -> Settings:
    """Returns a cached singleton instance of the configuration settings."""
    return Settings()


def resolve_database_url() -> str:
    import os
    residency = os.getenv("VALENCE_DATA_RESIDENCY", "US").strip().upper()
    if residency == "EU":
        return os.getenv(
            "DATABASE_URL_EU",
            os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./valence.db")
        ).strip()
    return os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./valence.db").strip()
