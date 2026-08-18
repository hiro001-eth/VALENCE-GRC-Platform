"""Notification Preferences — wire alerts to metric status changes.

Allows users to configure which metrics/thresholds trigger notifications
and through which channels (email, Slack, Teams, PagerDuty).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import AlertRecord, IntegrationSettings, User
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()


class NotificationPrefs(BaseModel):
    email_enabled: bool = True
    slack_enabled: bool = True
    teams_enabled: bool = True
    pagerduty_enabled: bool = True
    notify_on_amber: bool = True
    notify_on_red: bool = True
    notify_on_recovery: bool = True  # When metric goes Green again
    quiet_hours_start: int | None = None  # Hour (0-23)
    quiet_hours_end: int | None = None


@router.get("/channels")
async def get_notification_channels(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """List configured notification channels and their status."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = result.scalar_one_or_none()

    import os

    return {
        "channels": [
            {
                "id": "email",
                "name": "Email (SMTP)",
                "configured": bool(os.getenv("SMTP_HOST", "").strip()),
                "target": os.getenv("ALERT_TO_EMAIL", "not_set"),
                "icon": "📧",
            },
            {
                "id": "slack",
                "name": "Slack Webhook",
                "configured": bool(settings and settings.slack_webhook_url),
                "target": (settings.slack_webhook_url[:30] + "...") if settings and settings.slack_webhook_url else "not_configured",
                "icon": "💬",
            },
            {
                "id": "teams",
                "name": "Microsoft Teams",
                "configured": bool(settings and settings.teams_webhook_url),
                "target": (settings.teams_webhook_url[:30] + "...") if settings and settings.teams_webhook_url else "not_configured",
                "icon": "🟦",
            },
            {
                "id": "pagerduty",
                "name": "PagerDuty",
                "configured": bool(settings and settings.pagerduty_routing_key),
                "target": "configured" if settings and settings.pagerduty_routing_key else "not_configured",
                "icon": "🔔",
            },
        ],
        "alert_triggers": {
            "amber_threshold": "Metric crosses Amber RAG threshold",
            "red_threshold": "Metric crosses Red RAG threshold (critical SLA breach)",
            "recovery": "Metric returns to Green from Amber/Red",
            "evidence_gap": "Evidence chain integrity check failure",
            "control_failure": "Continuous control monitoring test failure",
        },
    }


@router.get("/history")
async def get_alert_history(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
    limit: int = 50,
) -> dict[str, Any]:
    """Get alert notification history for the tenant."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(AlertRecord)
        .where(AlertRecord.tenant_id == tenant_id)
        .order_by(AlertRecord.created_at.desc())
        .limit(limit)
    )
    alerts = result.scalars().all()

    return {
        "total": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "metric_id": a.metric_id,
                "metric_name": a.metric_name,
                "rag_status": a.rag_status,
                "severity": a.severity,
                "message": a.message,
                "channels_notified": a.channels_notified,
                "acknowledged": a.acknowledged,
                "acknowledged_by": a.acknowledged_by,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ],
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Acknowledge an alert to indicate it has been reviewed."""
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(AlertRecord).where(
            AlertRecord.id == alert_id,
            AlertRecord.tenant_id == tenant_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_by = current_user.username
    alert.acknowledged_at = datetime.now(UTC)
    await db.commit()

    return {
        "status": "acknowledged",
        "alert_id": alert_id,
        "acknowledged_by": current_user.username,
    }
