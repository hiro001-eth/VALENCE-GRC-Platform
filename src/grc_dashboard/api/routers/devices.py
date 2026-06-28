"""MDM / endpoint device compliance tracking."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import DeviceComplianceRecord, User
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

router = APIRouter()

DEMO_DEVICES = [
    ("DEV-001", "MacBook Pro — Alex", "alex.chen@company.com", "macos", True, True, "14.4", "compliant"),
    ("DEV-002", "ThinkPad — Sam", "sam.patel@company.com", "windows", True, True, "11 23H2", "compliant"),
    ("DEV-003", "iPhone — Jordan", "jordan.lee@company.com", "ios", True, True, "17.4", "compliant"),
    ("DEV-004", "Surface — Taylor", "taylor.kim@company.com", "windows", False, False, "10 22H2", "non_compliant"),
    ("DEV-005", "Linux Workstation", "devops@company.com", "linux", True, True, "Ubuntu 22.04", "compliant"),
]


class DeviceCreate(BaseModel):
    device_id: str
    device_name: str = ""
    owner_email: str = ""
    platform: str = "unknown"
    mdm_enrolled: bool = False
    disk_encrypted: bool = False
    os_version: str = ""
    compliance_status: str = "unknown"
    source: str = "manual"


async def _ensure_demo_devices(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(DeviceComplianceRecord.id).where(DeviceComplianceRecord.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return
    now = datetime.now(UTC)
    for dev_id, name, email, platform, mdm, enc, os_ver, status in DEMO_DEVICES:
        session.add(
            DeviceComplianceRecord(
                tenant_id=tenant_id,
                device_id=dev_id,
                device_name=name,
                owner_email=email,
                platform=platform,
                mdm_enrolled=mdm,
                disk_encrypted=enc,
                os_version=os_ver,
                compliance_status=status,
                last_seen_at=now - timedelta(hours=2),
                source="intune",
            )
        )
    await session.commit()


def _row(d: DeviceComplianceRecord) -> dict[str, Any]:
    return {
        "id": d.id,
        "device_id": d.device_id,
        "device_name": d.device_name,
        "owner_email": d.owner_email,
        "platform": d.platform,
        "mdm_enrolled": d.mdm_enrolled,
        "disk_encrypted": d.disk_encrypted,
        "os_version": d.os_version,
        "compliance_status": d.compliance_status,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "source": d.source,
    }


@router.get("/")
async def list_devices(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_devices(db, tenant_id)
    result = await db.execute(
        select(DeviceComplianceRecord)
        .where(DeviceComplianceRecord.tenant_id == tenant_id)
        .order_by(DeviceComplianceRecord.compliance_status)
    )
    return [_row(d) for d in result.scalars().all()]


@router.get("/summary")
async def device_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    devices = await list_devices(request, db, current_user)
    compliant = sum(1 for d in devices if d["compliance_status"] == "compliant")
    return {
        "total_devices": len(devices),
        "compliant": compliant,
        "non_compliant": len(devices) - compliant,
        "compliance_pct": round((compliant / len(devices)) * 100, 1) if devices else 0,
        "mdm_enrolled_pct": round(
            (sum(1 for d in devices if d["mdm_enrolled"]) / len(devices)) * 100, 1
        ) if devices else 0,
    }


@router.post("/", status_code=201)
async def register_device(
    body: DeviceCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    row = DeviceComplianceRecord(
        tenant_id=tenant_id,
        device_id=body.device_id,
        device_name=body.device_name,
        owner_email=body.owner_email,
        platform=body.platform,
        mdm_enrolled=body.mdm_enrolled,
        disk_encrypted=body.disk_encrypted,
        os_version=body.os_version,
        compliance_status=body.compliance_status,
        last_seen_at=datetime.now(UTC),
        source=body.source,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row(row)
