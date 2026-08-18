import os

import httpx
import structlog

logger = structlog.get_logger(__name__)


class TeamsNotifier:
    """Dispatches GRC alert cards to Microsoft Teams channel connectors."""

    def __init__(self) -> None:
        self.webhook_url = os.getenv("TEAMS_WEBHOOK_URL", "")

    async def send_alert(
        self,
        metric_id: str,
        metric_name: str,
        rag_status: str,
        message: str,
        webhook_url: str | None = None,
    ) -> bool:
        url = webhook_url or self.webhook_url
        if not url:
            logger.debug("teams_alert_skipped_no_webhook_url")
            return False

        color = "2EB886" if rag_status == "Green" else "DAA038" if rag_status == "Amber" else "A30200"
        emoji = "✅" if rag_status == "Green" else "⚠️" if rag_status == "Amber" else "🚨"

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": f"GRC Alert: {metric_id}",
            "sections": [
                {
                    "activityTitle": f"{emoji} GRC SLA Alert: {metric_name} ({metric_id})",
                    "activitySubtitle": f"Status: {rag_status.upper()}",
                    "facts": [
                        {"name": "Metric ID", "value": metric_id},
                        {"name": "Current Status", "value": rag_status},
                        {"name": "Details", "value": message}
                    ],
                    "markdown": True
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code in (200, 201):
                    logger.info("teams_alert_delivered", metric_id=metric_id)
                    return True
                logger.error("teams_alert_delivery_failed", code=resp.status_code, body=resp.text)
                return False
        except Exception as e:
            logger.error("teams_alert_exception", error=str(e))
            return False
