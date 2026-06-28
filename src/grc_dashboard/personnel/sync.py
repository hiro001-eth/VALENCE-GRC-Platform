"""Sync JML events from connected IdP integrations."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.db.models import PersonnelEvent
from grc_dashboard.integrations.secrets import merge_collector_config
from grc_dashboard.tenancy.constants import is_demo_tenant

logger = structlog.get_logger(__name__)


async def sync_jml_from_integrations(
    session: AsyncSession,
    tenant_id: str,
    connected_integrations: dict[str, Any] | None,
) -> int:
    """Pull recent user lifecycle signals from Okta and create personnel events."""
    if not connected_integrations or is_demo_tenant(tenant_id):
        return 0

    okta_cfg = connected_integrations.get("okta")
    if not okta_cfg or okta_cfg.get("status") != "connected":
        return 0

    metadata, secrets = merge_collector_config(okta_cfg)
    token = secrets.get("api_key")
    org_url = metadata.get("org_url", "").rstrip("/")
    if not token or not org_url:
        return 0

    created = 0
    headers = {"Authorization": f"SSWS {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(f"{org_url}/api/v1/users?limit=50", headers=headers)
            if res.status_code != 200:
                return 0
            users = res.json()
            for user in users:
                status = user.get("status", "")
                email = (user.get("profile") or {}).get("email", "")
                if not email:
                    continue
                event_type = "joiner" if status == "ACTIVE" else "leaver" if status in ("DEPROVISIONED", "SUSPENDED") else "mover"
                existing = await session.execute(
                    select(PersonnelEvent.id).where(
                        PersonnelEvent.tenant_id == tenant_id,
                        PersonnelEvent.employee_email == email.lower(),
                        PersonnelEvent.source == "okta_sync",
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    continue
                name = f"{(user.get('profile') or {}).get('firstName', '')} {(user.get('profile') or {}).get('lastName', '')}".strip()
                session.add(
                    PersonnelEvent(
                        id=f"JML-{uuid.uuid4().hex[:8].upper()}",
                        tenant_id=tenant_id,
                        event_type=event_type,
                        employee_email=email.lower(),
                        employee_name=name,
                        department=(user.get("profile") or {}).get("department", ""),
                        source="okta_sync",
                        notes=f"Synced from Okta status: {status}",
                    )
                )
                created += 1
    except Exception as exc:
        logger.warning("jml_sync_failed", tenant_id=tenant_id, error=str(exc))
    if created:
        await session.commit()
        logger.info("jml_synced", tenant_id=tenant_id, events=created)
    return created
