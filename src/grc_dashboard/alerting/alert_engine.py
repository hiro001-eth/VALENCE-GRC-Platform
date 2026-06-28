from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.alerting.email_notifier import EmailNotifier
from grc_dashboard.alerting.slack_notifier import SlackNotifier
from grc_dashboard.alerting.teams_notifier import TeamsNotifier
from grc_dashboard.alerting.pagerduty_notifier import PagerDutyNotifier
from grc_dashboard.db.models import AlertRecord, IntegrationSettings
from grc_dashboard.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)


class AlertEngine:
    """
    Alert Engine: checks metric states, determines SLA breaches,
    persists alerts to DB, and dispatches multi-channel alerts (Slack, Teams, PagerDuty, Email).
    """

    def __init__(self) -> None:
        self.slack = SlackNotifier()
        self.teams = TeamsNotifier()
        self.pagerduty = PagerDutyNotifier()
        self.email = EmailNotifier()

    async def process_metrics(self, run_id: str, metrics: list[dict[str, Any]]) -> None:
        """Evaluate run metrics and trigger alerts on SLA threshold violations (Amber/Red)."""
        tenant_id = "default"
        if metrics:
            # Safely extract from either model or dict
            first_m = metrics[0]
            if hasattr(first_m, "tenant_id"):
                tenant_id = getattr(first_m, "tenant_id")
            elif isinstance(first_m, dict):
                tenant_id = first_m.get("tenant_id", "default")

        async with AsyncSessionLocal() as db:
            # Query integration settings for this tenant
            settings_res = await db.execute(
                select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
            )
            settings = settings_res.scalar_one_or_none()

            slack_url = settings.slack_webhook_url if settings else None
            teams_url = settings.teams_webhook_url if settings else None
            pagerduty_key = settings.pagerduty_routing_key if settings else None

            for m in metrics:
                if isinstance(m, dict):
                    rag = m.get("rag_status", "Green")
                    metric_id = m.get("metric_id", "")
                    metric_name = m.get("metric_name", "")
                    message = m.get("narrative", "SLA Threshold limit breached.")
                else:
                    # It's a Pydantic object
                    rag = getattr(m, "rag_status", "Green")
                    metric_id = getattr(m, "metric_id", "")
                    metric_name = getattr(m, "metric_name", "")
                    message = getattr(m, "narrative", "SLA Threshold limit breached.")

                if rag not in ("Amber", "Red"):
                    continue

                # Avoid duplicate alerts for same metric in same run
                existing = await db.execute(
                    select(AlertRecord).where(
                        AlertRecord.run_id == run_id,
                        AlertRecord.metric_id == metric_id
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Trigger notifications
                channels = []
                if await self.slack.send_alert(metric_id, metric_name, rag, message, webhook_url=slack_url):
                    channels.append("slack")
                if await self.teams.send_alert(metric_id, metric_name, rag, message, webhook_url=teams_url):
                    channels.append("teams")
                if await self.pagerduty.send_alert(metric_id, metric_name, rag, message, routing_key=pagerduty_key):
                    channels.append("pagerduty")
                if await self.email.send_alert(metric_id, metric_name, rag, message):
                    channels.append("email")

                # Persist alert record to DB
                alert = AlertRecord(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    metric_id=metric_id,
                    metric_name=metric_name,
                    rag_status=rag,
                    severity="critical" if rag == "Red" else "high",
                    message=message,
                    channels_notified=channels,
                    acknowledged=False
                )
                db.add(alert)
                logger.info("alert_created", metric_id=metric_id, run_id=run_id, tenant_id=tenant_id, channels=channels)

            await db.commit()
