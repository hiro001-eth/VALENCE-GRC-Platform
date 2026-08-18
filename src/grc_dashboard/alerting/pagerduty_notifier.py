import os

import httpx
import structlog

logger = structlog.get_logger(__name__)


class PagerDutyNotifier:
    """Dispatches real-time security posture breach events to PagerDuty."""

    def __init__(self) -> None:
        self.routing_key = os.getenv("PAGERDUTY_ROUTING_KEY", "")

    async def send_alert(
        self,
        metric_id: str,
        metric_name: str,
        rag_status: str,
        message: str,
        routing_key: str | None = None,
    ) -> bool:
        key = routing_key or self.routing_key
        if not key:
            logger.debug("pagerduty_alert_skipped_no_routing_key")
            return False

        severity = "critical" if rag_status == "Red" else "warning" if rag_status == "Amber" else "info"
        payload = {
            "routing_key": key,
            "event_action": "trigger",
            "dedup_key": f"valence-grc-{metric_id}",
            "client": "VALENCE GRC Platform",
            "client_url": "http://localhost:8000",
            "payload": {
                "summary": f"🚨 VALENCE SLA Breach: {metric_name} is {rag_status.upper()}",
                "source": "valence-grc-dashboard",
                "severity": severity,
                "component": metric_id,
                "custom_details": {
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "status": rag_status,
                    "details": message,
                }
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://events.pagerduty.com/v2/enqueue", json=payload)
                if resp.status_code in (200, 202):
                    logger.info("pagerduty_alert_delivered", metric_id=metric_id)
                    return True
                logger.error("pagerduty_alert_delivery_failed", code=resp.status_code, body=resp.text)
                return False
        except Exception as e:
            logger.error("pagerduty_alert_exception", error=str(e))
            return False
