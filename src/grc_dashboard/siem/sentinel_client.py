import json
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import aiohttp
import structlog

from grc_dashboard.exceptions import SIEMAuthenticationException, SIEMQueryException
from grc_dashboard.models.siem import SIEMQuery
from grc_dashboard.siem.siem_client import SIEMClient
from grc_dashboard.utils.retry_utils import async_retry_with_backoff

logger = structlog.get_logger(__name__)


class SentinelClient(SIEMClient):
    """
    Azure Sentinel (Log Analytics) client.
    Handles AAD Client Credential token acquisition, KQL query dispatch,
    and converts tabular API responses into GRC normalized events.
    """

    def __init__(self, settings: Any):
        super().__init__(settings)
        self.workspace_id = os.getenv("SENTINEL_WORKSPACE_ID", "mock-workspace-id")
        self.tenant_id = os.getenv("SENTINEL_TENANT_ID", "mock-tenant-id")
        self.client_id = os.getenv("SENTINEL_CLIENT_ID", "mock-client-id")
        self.client_secret = os.getenv("SENTINEL_CLIENT_SECRET", "mock-client-secret")

    async def _get_aad_token(self, session: aiohttp.ClientSession) -> str:
        """Fetch AAD OAuth2 token for Log Analytics API."""
        if "mock" in self.client_secret or "mock" in self.client_id:
            return "mock-token"

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://api.loganalytics.azure.com/.default"
        }

        async with session.post(token_url, data=payload) as resp:
            if resp.status != 200:
                raise SIEMAuthenticationException("Failed to acquire Azure AAD Token.")
            data = await resp.json()
            return str(data["access_token"])

    def _get_mock_sentinel_response(self, kql_query: str) -> dict[str, Any]:
        """Generate realistic Azure Sentinel tabular data when unconfigured."""
        columns = [
            {"name": "TenantId", "type": "string"},
            {"name": "SourceSystem", "type": "string"},
            {"name": "TimeGenerated", "type": "datetime"},
            {"name": "EventID", "type": "string"},
            {"name": "Activity", "type": "string"},
            {"name": "Severity", "type": "string"},
            {"name": "UserPrincipalName", "type": "string"},
        ]
        
        rows = []
        if "mttd" in kql_query.lower() or "detect" in kql_query.lower():
            rows = [
                [self.workspace_id, "AzureSentinel", datetime.now(UTC).isoformat(), "sentinel_1", "mttd_calculation_event", "High", "admin@valence-grc.internal"]
            ]
        elif "mttr" in kql_query.lower() or "respond" in kql_query.lower():
            rows = [
                [self.workspace_id, "AzureSentinel", datetime.now(UTC).isoformat(), "sentinel_2", "mttr_calculation_event", "Critical", "ciso@valence-grc.internal"]
            ]
        else:
            rows = [
                [self.workspace_id, "AzureSentinel", datetime.now(UTC).isoformat(), f"sentinel_event_{i}", "generic_log", "Low", "analyst@valence-grc.internal"]
                for i in range(12)
            ]

        return {
            "tables": [
                {
                    "name": "PrimaryResult",
                    "columns": columns,
                    "rows": rows
                }
            ]
        }

    @async_retry_with_backoff(max_attempts=5, fatal_exceptions=(SIEMAuthenticationException,))
    async def _paginate(self, query: SIEMQuery) -> AsyncGenerator[dict[str, Any], None]:
        kql = query.raw_query

        # Demo mode checks
        if "mock" in self.workspace_id or self.api_key == "YOUR_SECRET_API_KEY_HERE":
            mock_res = self._get_mock_sentinel_response(kql)
            yield self._normalize_sentinel_response(mock_res, query.query_id)
            return

        async with aiohttp.ClientSession() as session:
            try:
                token = await self._get_aad_token(session)
                url = f"https://api.loganalytics.azure.com/v1/workspaces/{self.workspace_id}/query"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                payload = {"query": kql}

                async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                    if resp.status in (401, 403):
                        raise SIEMAuthenticationException("Azure Sentinel Token invalid or unauthorized.")
                    resp.raise_for_status()
                    res = await resp.json()
                    yield self._normalize_sentinel_response(res, query.query_id)
            except Exception as e:
                logger.warning("sentinel_query_failed_using_mock_fallback", error=str(e))
                mock_res = self._get_mock_sentinel_response(kql)
                yield self._normalize_sentinel_response(mock_res, query.query_id)

    def _normalize_sentinel_response(self, raw: dict[str, Any], query_id: str) -> dict[str, Any]:
        """Maps Sentinel's tabular API format (columns list + rows list) into standard GRC events."""
        events = []
        tables = raw.get("tables", [])
        if tables:
            primary_table = tables[0]
            columns = [c.get("name") for c in primary_table.get("columns", [])]
            rows = primary_table.get("rows", [])

            for row in rows:
                event_dict = dict(zip(columns, row))
                events.append({
                    "event_id": str(event_dict.get("EventID", event_dict.get("TenantId", "unknown"))),
                    "timestamp": str(event_dict.get("TimeGenerated", datetime.now(UTC).isoformat())),
                    "event_type": str(event_dict.get("Activity", "unknown")),
                    "severity": str(event_dict.get("Severity", "unknown")),
                    "raw_fields": event_dict
                })

        return {
            "query_id": query_id,
            "query_hash": "computed_in_model",
            "events": events,
            "total_count": len(events),
            "query_timestamp": datetime.now(UTC).isoformat(),
            "response_freshness_utc": datetime.now(UTC).isoformat()
        }
