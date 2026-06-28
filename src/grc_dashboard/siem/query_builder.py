import json
from typing import Any

from grc_dashboard.config import Settings
from grc_dashboard.models.metric import MetricDefinition
from grc_dashboard.models.siem import SIEMQuery
from grc_dashboard.utils.hash_utils import sha256_bytes


class QueryBuilder:
    """
    Builds metric-specific SIEM queries and computes query_hash.
    Supports Elastic API syntax (winner from R1:Q1).
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.index_alerts = "soc-alerts-*"
        self.index_incidents = "soc-incidents-*"

    def build_query(self, metric_def: MetricDefinition) -> SIEMQuery:
        """Routes to specific builder based on KPI type."""
        raw_query_dict: dict[str, Any] = {}
        
        # Simplified mappings per R1:Q2 spec
        if "MTTD" in metric_def.metric_id:
            raw_query_dict = self._build_mttd_query()
        elif "MTTR" in metric_def.metric_id:
            raw_query_dict = self._build_mttr_query()
        elif "Volume" in metric_def.metric_id:
            raw_query_dict = self._build_alert_volume_query()
        elif "FPR" in metric_def.metric_id:
            raw_query_dict = self._build_fpr_query()
        elif "Coverage" in metric_def.metric_id:
            raw_query_dict = self._build_open_incidents_query()
        else:
            # Fallback for generic count queries
            raw_query_dict = {"query": {"match_all": {}}, "size": 0}

        raw_query_str = json.dumps(raw_query_dict, sort_keys=True)
        query_id = f"q_{metric_def.metric_id.lower()}_{self._compute_query_hash(raw_query_str)[:8]}"
        
        return SIEMQuery(query_id=query_id, raw_query=raw_query_str)

    def _build_mttd_query(self) -> dict[str, Any]:
        return {
            "index": self.index_alerts,
            "query": {"range": {"creation_time": {"gte": "now-30d/d"}}},
            "aggs": {
                "mttd": {
                    "avg": {
                        "script": "doc['first_action_time'].value.millis - doc['creation_time'].value.millis"
                    }
                }
            },
            "size": 0
        }

    def _build_mttr_query(self) -> dict[str, Any]:
        return {
            "index": self.index_incidents,
            "query": {"range": {"creation_time": {"gte": "now-30d/d"}}},
            "aggs": {
                "mttr": {
                    "avg": {
                        "script": "doc['closure_time'].value.millis - doc['creation_time'].value.millis"
                    }
                }
            },
            "size": 0
        }

    def _build_alert_volume_query(self) -> dict[str, Any]:
        return {
            "index": self.index_alerts,
            "query": {"range": {"creation_time": {"gte": "now-24h"}}},
            "size": 0
        }

    def _build_fpr_query(self) -> dict[str, Any]:
        return {
            "index": self.index_alerts,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"classification_label": ["true_positive", "false_positive"]}},
                        {"range": {"creation_time": {"gte": "now-7d/d"}}}
                    ]
                }
            },
            "aggs": {
                "classifications": {
                    "terms": {"field": "classification_label"}
                }
            },
            "size": 0
        }

    def _build_open_incidents_query(self) -> dict[str, Any]:
        return {
            "index": self.index_incidents,
            "query": {
                "terms": {"status": ["open", "investigating"]}
            },
            "size": 0
        }

    def _compute_query_hash(self, raw_query: str) -> str:
        return sha256_bytes(raw_query.encode("utf-8"))
