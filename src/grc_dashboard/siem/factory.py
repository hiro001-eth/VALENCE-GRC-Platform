"""SIEM client factory and tenant integration helpers."""
from __future__ import annotations

from typing import Any

from pydantic import AnyHttpUrl, SecretStr

from grc_dashboard.config import Settings, SIEMSettings, get_settings
from grc_dashboard.db.models import IntegrationSettings
from grc_dashboard.siem.elastic_client import ElasticClient
from grc_dashboard.siem.sentinel_client import SentinelClient
from grc_dashboard.siem.siem_client import SIEMClient
from grc_dashboard.siem.splunk_client import SplunkClient


def normalize_siem_type(siem_type: str) -> str:
    t = (siem_type or "").strip().lower()
    if t in ("elastic", "elastic security", "elasticsearch", "elk"):
        return "Elastic"
    if t in ("splunk", "splunk enterprise"):
        return "Splunk"
    if t in ("csv", "file", "upload"):
        return "CSV"
    if t in ("wazuh", "opensearch", "wazuh indexer"):
        return "Wazuh"
    if t in ("sentinel", "azure sentinel", "azure_sentinel", "log analytics"):
        return "Sentinel"
    if t in ("demo", "sandbox", "none", ""):
        return ""
    return siem_type


def is_siem_configured(settings: IntegrationSettings | None) -> bool:
    if not settings:
        return False
    siem_type = normalize_siem_type(settings.siem_type)
    if siem_type == "CSV":
        return True
    if not siem_type:
        return False
    return bool(settings.siem_url and settings.siem_api_key)


def build_tenant_settings(integration: IntegrationSettings) -> Settings:
    """Overlay per-tenant SIEM credentials onto global settings."""
    base = get_settings()
    siem_type = normalize_siem_type(integration.siem_type) or "Elastic"
    url = integration.siem_url or str(base.siem.base_url)
    key = integration.siem_api_key or base.siem.api_key.get_secret_value()
    siem = SIEMSettings(
        siem_type=siem_type,  # type: ignore[arg-type]
        base_url=AnyHttpUrl(url),
        api_key=SecretStr(key),
        data_ttl_minutes=base.siem.data_ttl_minutes,
        max_results_per_page=base.siem.max_results_per_page,
        query_timeout_seconds=base.siem.query_timeout_seconds,
    )
    return base.model_copy(update={"siem": siem})


def create_siem_client(settings: Settings) -> SIEMClient:
    siem_type = normalize_siem_type(settings.siem.siem_type)
    if siem_type == "Splunk":
        return SplunkClient(settings)
    if siem_type == "Sentinel":
        return SentinelClient(settings)
    # Wazuh Indexer is OpenSearch/Elasticsearch-compatible
    return ElasticClient(settings)
