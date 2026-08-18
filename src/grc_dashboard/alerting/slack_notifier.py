import os

import httpx
import structlog

logger = structlog.get_logger(__name__)


class SlackNotifier:
    """Dispatches beautiful GRC alert notification messages to Slack via Webhooks."""

    def __init__(self) -> None:
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")

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
            logger.debug("slack_alert_skipped_no_webhook_url")
            return False

        color = "#2EB886" if rag_status == "Green" else "#DAA038" if rag_status == "Amber" else "#A30200"
        emoji = "✅" if rag_status == "Green" else "⚠️" if rag_status == "Amber" else "🚨"

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*GRC SLA Breach Notification* {emoji}\n*Metric:* {metric_name} (`{metric_id}`)\n*Status:* *{rag_status}*"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Detail:* {message}"
                            }
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": "🔮 *VALENCE GRC Security Dashboard* · Automated SLA Sentinel"
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info("slack_alert_delivered", metric_id=metric_id)
                    return True
                logger.error("slack_alert_delivery_failed", code=resp.status_code, body=resp.text)
                return False
        except Exception as e:
            logger.error("slack_alert_exception", error=str(e))
            return False
