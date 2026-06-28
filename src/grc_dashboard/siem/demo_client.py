import random
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from grc_dashboard.models.siem import SIEMQuery
from grc_dashboard.siem.siem_client import SIEMClient

logger = structlog.get_logger(__name__)


class DemoClient(SIEMClient):
    """
    Demo/Mock SIEM client producing realistic, synthetically generated security logs
    to allow full GRC dashboard operation and testing without external servers.
    """

    async def _paginate(self, query: SIEMQuery) -> AsyncGenerator[dict[str, Any], None]:
        """Generate high-quality mock data for testing."""
        random.seed(42)  # Maintain deterministic outcomes for standard checks
        events = []
        q_lower = query.raw_query.lower()

        if "mttd" in q_lower or "detect" in q_lower:
            # Generate logs representing detection latency
            for i in range(5):
                start = datetime.now(UTC) - timedelta(days=i, hours=random.randint(1, 4))
                # MTTD between 5 and 25 minutes
                detect_delay = random.randint(5, 25)
                end = start + timedelta(minutes=detect_delay)
                events.append({
                    "event_id": f"demo_mttd_{i}",
                    "timestamp": end.isoformat(),
                    "creation_time": start.isoformat(),
                    "first_action_time": end.isoformat(),
                    "event_type": "soc-alerts",
                    "severity": "high",
                })
        elif "mttr" in q_lower or "respond" in q_lower:
            # Generate logs representing response/resolution latency
            for i in range(5):
                start = datetime.now(UTC) - timedelta(days=i, hours=random.randint(2, 6))
                # MTTR between 20 and 90 minutes
                respond_delay = random.randint(20, 90)
                end = start + timedelta(minutes=respond_delay)
                events.append({
                    "event_id": f"demo_mttr_{i}",
                    "timestamp": end.isoformat(),
                    "creation_time": start.isoformat(),
                    "closure_time": end.isoformat(),
                    "event_type": "soc-incidents",
                    "severity": "critical",
                })
        elif "false_positive" in q_lower or "fpr" in q_lower:
            # Generate false positive vs true positive ratio alerts
            for i in range(18):
                events.append({
                    "event_id": f"demo_fp_{i}",
                    "timestamp": (datetime.now(UTC) - timedelta(hours=i)).isoformat(),
                    "classification_label": "false_positive",
                    "event_type": "soc-alerts",
                    "severity": "medium",
                })
            for i in range(82):
                events.append({
                    "event_id": f"demo_tp_{i}",
                    "timestamp": (datetime.now(UTC) - timedelta(hours=i)).isoformat(),
                    "classification_label": "true_positive",
                    "event_type": "soc-alerts",
                    "severity": "high",
                })
        elif "patch" in q_lower or "cve" in q_lower:
            # Generate vulnerability patch lag metrics
            for i in range(10):
                discovered = datetime.now(UTC) - timedelta(days=random.randint(5, 15))
                patched = datetime.now(UTC) - timedelta(days=random.randint(0, 4))
                events.append({
                    "event_id": f"demo_cve_{i}",
                    "timestamp": patched.isoformat(),
                    "discovery_time": discovered.isoformat(),
                    "patch_time": patched.isoformat(),
                    "event_type": "vuln-scans",
                    "severity": "high",
                })
        else:
            # Generic logs fallback
            for i in range(30):
                events.append({
                    "event_id": f"demo_event_{i}",
                    "timestamp": (datetime.now(UTC) - timedelta(minutes=i*15)).isoformat(),
                    "event_type": "generic-syslog",
                    "severity": "info",
                })

        normalized_batch = {
            "query_id": query.query_id,
            "query_hash": "computed_in_model",
            "events": events,
            "total_count": len(events),
            "query_timestamp": datetime.now(UTC).isoformat(),
            "response_freshness_utc": datetime.now(UTC).isoformat()
        }
        yield normalized_batch
