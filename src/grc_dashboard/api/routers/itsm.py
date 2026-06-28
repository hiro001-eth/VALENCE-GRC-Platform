"""ITSM ticket sync and CMDB — ServiceNow + Jira parity."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst
from grc_dashboard.db.models import CmdbAsset, IntegrationSettings, ItsTicketRecord, RemediationTask, User
from grc_dashboard.db.session import get_db
from grc_dashboard.orchestration.itsm_sync import sync_cmdb_from_integrations, sync_remediation_to_itsm

router = APIRouter()


class CmdbSyncRequest(BaseModel):
    bu_id: str | None = None


@router.get("/providers")
async def list_itsm_providers(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = res.scalar_one_or_none()
    connected = dict(settings.connected_integrations or {}) if settings else {}
    providers = []
    for pid, label in [("jira", "Atlassian Jira"), ("servicenow", "ServiceNow")]:
        entry = connected.get(pid, {})
        providers.append({
            "id": pid,
            "name": label,
            "connected": entry.get("status") == "connected",
            "auth_method": entry.get("auth_method"),
            "capabilities": ["incident", "remediation_sync", "cmdb"] if pid == "servicenow" else ["incident", "remediation_sync"],
        })
    return {"providers": providers, "cmdb_enabled": True}


@router.get("/tickets")
async def list_itsm_tickets(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(ItsTicketRecord)
        .where(ItsTicketRecord.tenant_id == tenant_id)
        .order_by(ItsTicketRecord.synced_at.desc())
        .limit(100)
    )
    tickets = [
        {
            "id": t.id,
            "provider": t.provider,
            "external_key": t.external_key,
            "status": t.status,
            "priority": t.priority,
            "summary": t.summary,
            "url": t.url,
            "remediation_task_id": t.remediation_task_id,
            "synced_at": t.synced_at.isoformat(),
        }
        for t in result.scalars().all()
    ]
    return {"tickets": tickets, "total": len(tickets)}


@router.post("/sync/remediation")
async def sync_all_remediation_tickets(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    """Push open remediation tasks to Jira or ServiceNow."""
    tenant_id = get_tenant_id(request)
    settings_res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = settings_res.scalar_one_or_none()

    tasks_res = await db.execute(
        select(RemediationTask).where(
            RemediationTask.tenant_id == tenant_id,
            RemediationTask.status.notin_(["completed", "cancelled"]),
            RemediationTask.external_ticket_id.is_(None),
        )
    )
    tasks = tasks_res.scalars().all()
    synced = 0
    for task in tasks:
        ticket = await sync_remediation_to_itsm(db, tenant_id, task, settings)
        if ticket:
            synced += 1
    await db.commit()
    return {"synced": synced, "message": f"Created {synced} ITSM ticket(s) from remediation tasks."}


@router.get("/cmdb/assets")
async def list_cmdb_assets(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
    bu_id: str | None = None,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    query = select(CmdbAsset).where(CmdbAsset.tenant_id == tenant_id)
    if bu_id:
        query = query.where(CmdbAsset.bu_id == bu_id)
    result = await db.execute(query.order_by(CmdbAsset.criticality.desc()))
    assets = [
        {
            "id": a.id,
            "name": a.name,
            "asset_type": a.asset_type,
            "owner": a.owner,
            "criticality": a.criticality,
            "source_integration": a.source_integration,
            "external_id": a.external_id,
            "bu_id": a.bu_id,
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        }
        for a in result.scalars().all()
    ]
    return {"assets": assets, "total": len(assets)}


@router.post("/sync/ticket-status")
async def sync_ticket_status_from_itsm(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    """Bidirectional sync — pull latest status from ServiceNow for open tickets."""
    from grc_dashboard.orchestration.itsm_sync import sync_servicenow_ticket_status

    tenant_id = get_tenant_id(request)
    settings_res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = settings_res.scalar_one_or_none()
    sn = dict((settings.connected_integrations or {}).get("servicenow", {})) if settings else {}
    if sn.get("status") != "connected":
        raise HTTPException(status_code=400, detail="ServiceNow not connected")

    tickets_res = await db.execute(
        select(ItsTicketRecord).where(
            ItsTicketRecord.tenant_id == tenant_id,
            ItsTicketRecord.provider == "servicenow",
            ItsTicketRecord.status.notin_(["closed", "resolved"]),
        )
    )
    updated = 0
    for ticket in tickets_res.scalars().all():
        status = await sync_servicenow_ticket_status(
            db, tenant_id, ticket, sn.get("secrets") or {}, sn.get("metadata") or {}
        )
        if status:
            updated += 1
    await db.commit()
    return {"updated": updated, "message": f"Synced status for {updated} ServiceNow ticket(s)."}


@router.post("/cmdb/sync")
async def sync_cmdb(
    body: CmdbSyncRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    settings_res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = settings_res.scalar_one_or_none()
    assets = await sync_cmdb_from_integrations(db, tenant_id, settings, body.bu_id)
    await db.commit()
    return {"synced": len(assets), "assets": [{"id": a.id, "name": a.name, "criticality": a.criticality} for a in assets]}
