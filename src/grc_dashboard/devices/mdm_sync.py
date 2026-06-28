"""Sync MDM devices from Jamf/Kandji into device compliance table."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.collectors.jamf_collector import fetch_jamf_devices
from grc_dashboard.collectors.kandji_collector import fetch_kandji_devices
from grc_dashboard.db.models import DeviceComplianceRecord
from grc_dashboard.integrations.secrets import merge_collector_config

logger = structlog.get_logger(__name__)

_MDM_FETCHERS = {
    "jamf": fetch_jamf_devices,
    "kandji": fetch_kandji_devices,
}


async def sync_mdm_devices(
    session: AsyncSession,
    tenant_id: str,
    connected_integrations: dict[str, Any] | None,
) -> int:
    if not connected_integrations:
        return 0

    synced = 0
    for mdm_id, fetcher in _MDM_FETCHERS.items():
        cfg = connected_integrations.get(mdm_id)
        if not cfg or cfg.get("status") != "connected":
            continue
        metadata, secrets = merge_collector_config(cfg)
        metadata["tenant_id"] = tenant_id
        try:
            devices = await fetcher(metadata, secrets)
            for d in devices:
                existing = await session.execute(
                    select(DeviceComplianceRecord).where(
                        DeviceComplianceRecord.tenant_id == tenant_id,
                        DeviceComplianceRecord.device_id == d["device_id"],
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.device_name = d.get("device_name", row.device_name)
                    row.compliance_status = d.get("compliance_status", row.compliance_status)
                    row.last_seen_at = datetime.now(UTC)
                else:
                    session.add(
                        DeviceComplianceRecord(
                            tenant_id=tenant_id,
                            device_id=d["device_id"],
                            device_name=d.get("device_name", ""),
                            owner_email=d.get("owner_email", ""),
                            platform=d.get("platform", "unknown"),
                            mdm_enrolled=d.get("mdm_enrolled", True),
                            disk_encrypted=d.get("disk_encrypted", False),
                            os_version=d.get("os_version", ""),
                            compliance_status=d.get("compliance_status", "unknown"),
                            last_seen_at=datetime.now(UTC),
                            source=mdm_id,
                        )
                    )
                synced += 1
        except Exception as exc:
            logger.warning("mdm_sync_failed", mdm=mdm_id, error=str(exc))

    if synced:
        await session.commit()
        logger.info("mdm_devices_synced", tenant_id=tenant_id, count=synced)
    return synced
