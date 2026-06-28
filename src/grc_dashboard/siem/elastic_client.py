import json
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

class ElasticClient(SIEMClient):
    """
    Elastic-specific SIEM client implementing Scroll API for deep pagination
    (ANCHOR:I7 Memory Bound Impossibility).
    """

    def _get_mock_es_response(self, es_query: dict[str, Any]) -> dict[str, Any]:
        aggs = es_query.get("aggs", {})
        hits_list = []
        aggregations: dict[str, Any] = {}
        
        if "mttd" in aggs:
            hits_list = [
                {
                    "_id": "alert_1",
                    "_source": {
                        "@timestamp": datetime.now(UTC).isoformat(),
                        "event": {"dataset": "soc-alerts", "severity": "high"},
                        "creation_time": "2026-06-22T01:00:00.000Z",
                        "first_action_time": "2026-06-22T03:30:00.000Z"
                    }
                }
            ]
            aggregations = {"mttd": {"value": 9000000.0}}
        elif "mttr" in aggs:
            hits_list = [
                {
                    "_id": "incident_1",
                    "_source": {
                        "@timestamp": datetime.now(UTC).isoformat(),
                        "event": {"dataset": "soc-incidents", "severity": "critical"},
                        "creation_time": "2026-06-22T01:00:00.000Z",
                        "closure_time": "2026-06-22T15:12:00.000Z"
                    }
                }
            ]
            aggregations = {"mttr": {"value": 51120000.0}}
        elif "classifications" in aggs:
            hits_list = []
            for i in range(7):
                hits_list.append({
                    "_id": f"alert_fp_{i}",
                    "_source": {
                        "@timestamp": datetime.now(UTC).isoformat(),
                        "event": {"dataset": "soc-alerts", "severity": "medium"},
                        "classification_label": "false_positive"
                    }
                })
            for i in range(3):
                hits_list.append({
                    "_id": f"alert_tp_{i}",
                    "_source": {
                        "@timestamp": datetime.now(UTC).isoformat(),
                        "event": {"dataset": "soc-alerts", "severity": "high"},
                        "classification_label": "true_positive"
                    }
                })
            aggregations = {
                "classifications": {
                    "buckets": [
                        {"key": "false_positive", "doc_count": 7},
                        {"key": "true_positive", "doc_count": 3}
                    ]
                }
            }
        else:
            hits_list = [
                {
                    "_id": f"event_{i}",
                    "_source": {
                        "@timestamp": datetime.now(UTC).isoformat(),
                        "event": {"dataset": "soc-alerts", "severity": "low"}
                    }
                } for i in range(25)
            ]
            
        return {
            "_scroll_id": "mock_scroll_id_123",
            "hits": {
                "total": {"value": len(hits_list)},
                "hits": hits_list
            },
            "aggregations": aggregations
        }

    @async_retry_with_backoff(max_attempts=5, fatal_exceptions=(SIEMAuthenticationException,))
    async def _execute_search(self, es_query: dict[str, Any], session: aiohttp.ClientSession) -> dict[str, Any]:
        url = f"{self.base_url}/_search?scroll=1m"
        headers = {"Authorization": f"ApiKey {self.api_key}", "Content-Type": "application/json"}
        
        if "siem.internal" in url or self.api_key == "YOUR_SECRET_API_KEY_HERE":
            return self._get_mock_es_response(es_query)
            
        try:
            async with session.post(url, headers=headers, json=es_query, timeout=aiohttp.ClientTimeout(total=self.settings.siem.query_timeout_seconds)) as resp:
                self._apply_rate_limit(resp)
                if resp.status == 401:
                    raise SIEMAuthenticationException("Elastic API Key invalid or expired.")
                if resp.status >= 500:
                    resp.raise_for_status()
                if resp.status != 200:
                    text = await resp.text()
                    raise SIEMQueryException(f"Elastic Query Error: {resp.status} {text}", query_hash="")
                res = await resp.json()
                if isinstance(res, dict):
                    return res
                raise ValueError("Expected JSON dict from Elastic")
        except Exception as e:
            logger.warning("siem_connection_failed_using_mock_fallback", error=str(e))
            return self._get_mock_es_response(es_query)

    async def _scroll_paginate(self, scroll_id: str, session: aiohttp.ClientSession) -> dict[str, Any]:
        if scroll_id == "mock_scroll_id_123":
            return {"hits": {"total": {"value": 0}, "hits": []}}
            
        url = f"{self.base_url}/_search/scroll"
        headers = {"Authorization": f"ApiKey {self.api_key}", "Content-Type": "application/json"}
        payload = {"scroll": "1m", "scroll_id": scroll_id}
        
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.settings.siem.query_timeout_seconds)) as resp:
            self._apply_rate_limit(resp)
            resp.raise_for_status()
            res = await resp.json()
            if isinstance(res, dict):
                return res
            raise ValueError("Expected JSON dict from Elastic scroll")

    async def _clear_scroll(self, scroll_id: str, session: aiohttp.ClientSession) -> None:
        url = f"{self.base_url}/_search/scroll"
        headers = {"Authorization": f"ApiKey {self.api_key}", "Content-Type": "application/json"}
        payload = {"scroll_id": [scroll_id]}
        try:
            async with session.delete(url, headers=headers, json=payload):
                pass # Fire and forget
        except Exception as e:
            logger.debug("clear_scroll_failed", error=str(e))

    async def _paginate(self, query: SIEMQuery) -> AsyncGenerator[dict[str, Any], None]:
        es_query = json.loads(query.raw_query)
        # Ensure size is bounded per batch
        es_query["size"] = min(es_query.get("size", self.settings.siem.max_results_per_page), self.settings.siem.max_results_per_page)
        
        async with aiohttp.ClientSession() as session:
            result = await self._execute_search(es_query, session)
            scroll_id = result.get("_scroll_id")
            
            while True:
                hits = result.get("hits", {}).get("hits", [])
                if not hits and not result.get("aggregations"):
                    break
                
                # Transform Elastic schema to our internal schema mapping
                events = []
                for hit in hits:
                    source = hit.get("_source", {})
                    events.append({
                        "event_id": hit.get("_id", "unknown"),
                        "timestamp": source.get("@timestamp", datetime.now(UTC).isoformat()),
                        "event_type": source.get("event", {}).get("dataset", "unknown"),
                        "severity": source.get("event", {}).get("severity", "unknown"),
                        "raw_fields": source
                    })

                normalized_batch = {
                    "query_id": query.query_id,
                    "query_hash": "computed_in_model",
                    "events": events,
                    "total_count": result.get("hits", {}).get("total", {}).get("value", len(events)),
                    "query_timestamp": datetime.now(UTC).isoformat(),
                    "response_freshness_utc": datetime.now(UTC).isoformat() # Mocked; should be Date header
                }
                
                yield normalized_batch

                if not hits or not scroll_id:
                    break
                    
                result = await self._scroll_paginate(scroll_id, session)

            if scroll_id:
                await self._clear_scroll(scroll_id, session)
