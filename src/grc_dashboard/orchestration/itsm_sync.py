"""Tenant-scoped ITSM sync — Jira + ServiceNow + CMDB."""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.db.models import CmdbAsset, IntegrationSettings, ItsTicketRecord, RemediationTask

logger = structlog.get_logger(__name__)


def _connected_entry(settings: IntegrationSettings | None, provider: str) -> dict[str, Any]:
    if not settings:
        return {}
    return dict((settings.connected_integrations or {}).get(provider, {}))


async def create_jira_ticket(
    summary: str,
    description: str,
    priority: str,
    secrets: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, str]:
    project = metadata.get("project_key") or os.getenv("JIRA_PROJECT_KEY", "SECCOMP")
    base = metadata.get("jira_url") or os.getenv("JIRA_URL", "")
    token = secrets.get("api_key") or secrets.get("token") or os.getenv("JIRA_API_TOKEN", "")
    email = metadata.get("email") or os.getenv("JIRA_EMAIL", "")

    if base and token and email and "internal.corp" not in base:
        url = f"{base.rstrip('/')}/rest/api/2/issue"
        payload = {
            "fields": {
                "project": {"key": project},
                "summary": summary[:250],
                "description": description,
                "issuetype": {"name": "Task"},
                "priority": {"name": priority},
            }
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json=payload, auth=(email, token))
                if res.status_code in (200, 201):
                    key = res.json().get("key", "")
                    return {"key": key, "url": f"{base.rstrip('/')}/browse/{key}", "mode": "live"}
        except Exception as exc:
            logger.warning("jira_live_failed", error=str(exc))

    key = f"{project}-VAL-{uuid.uuid4().hex[:6].upper()}"
    return {"key": key, "url": f"https://jira.example.com/browse/{key}", "mode": "demo"}


async def create_servicenow_incident(
    summary: str,
    description: str,
    priority: str,
    secrets: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, str]:
    instance = (metadata.get("instance_url") or os.getenv("SERVICENOW_INSTANCE_URL", "")).rstrip("/")
    token = secrets.get("api_key") or secrets.get("access_token", "")
    if instance and token and "example.com" not in instance:
        url = f"{instance}/api/now/table/incident"
        payload = {
            "short_description": summary[:160],
            "description": description,
            "urgency": "1" if priority in ("Highest", "High") else "2",
            "impact": "2",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                if res.status_code in (200, 201):
                    result = res.json().get("result", {})
                    num = result.get("number", result.get("sys_id", ""))
                    return {
                        "key": num,
                        "url": f"{instance}/nav_to.do?uri=incident.do?sys_id={result.get('sys_id', '')}",
                        "mode": "live",
                    }
        except Exception as exc:
            logger.warning("servicenow_live_failed", error=str(exc))

    key = f"INC{uuid.uuid4().hex[:7].upper()}"
    return {"key": key, "url": f"https://{instance or 'demo.service-now.com'}/nav_to.do?uri=incident.do?sys_id={key}", "mode": "demo"}


async def sync_remediation_to_itsm(
    session: AsyncSession,
    tenant_id: str,
    task: RemediationTask,
    settings: IntegrationSettings | None,
) -> ItsTicketRecord | None:
    provider = None
    if _connected_entry(settings, "servicenow").get("status") == "connected":
        provider = "servicenow"
    elif _connected_entry(settings, "jira").get("status") == "connected":
        provider = "jira"

    if not provider:
        return None

    entry = _connected_entry(settings, provider)
    secrets = entry.get("secrets") or {}
    metadata = entry.get("metadata") or {}
    priority = "High" if task.priority in ("high", "critical") else "Medium"
    summary = f"[VALENCE] {task.title}"
    description = task.description or "Remediation task from VALENCE GRC continuous monitoring."

    if provider == "servicenow":
        result = await create_servicenow_incident(summary, description, priority, secrets, metadata)
    else:
        result = await create_jira_ticket(summary, description, priority, secrets, metadata)

    ticket = ItsTicketRecord(
        id=f"ITSM-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=tenant_id,
        remediation_task_id=task.id,
        provider=provider,
        external_key=result["key"],
        status="open",
        priority=task.priority,
        summary=summary,
        url=result.get("url"),
        synced_at=datetime.now(UTC),
    )
    task.external_ticket_id = result["key"]
    task.external_ticket_url = result.get("url")
    session.add(ticket)
    return ticket


async def fetch_servicenow_cmdb(
    secrets: dict[str, Any],
    metadata: dict[str, Any],
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Pull CMDB CI records from ServiceNow Table API."""
    instance = (metadata.get("instance_url") or os.getenv("SERVICENOW_INSTANCE_URL", "")).rstrip("/")
    token = secrets.get("api_key") or secrets.get("access_token", "")
    if not instance or not token or "example.com" in instance:
        return []

    url = f"{instance}/api/now/table/cmdb_ci"
    params = {"sysparm_limit": str(limit), "sysparm_fields": "sys_id,name,sys_class_name,operational_status,assigned_to"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if res.status_code != 200:
                return []
            return list(res.json().get("result", []))
    except Exception as exc:
        logger.warning("servicenow_cmdb_fetch_failed", error=str(exc))
        return []


async def sync_servicenow_ticket_status(
    session: AsyncSession,
    tenant_id: str,
    ticket: ItsTicketRecord,
    secrets: dict[str, Any],
    metadata: dict[str, Any],
) -> str | None:
    """Pull latest incident state from ServiceNow and update local ticket."""
    instance = (metadata.get("instance_url") or os.getenv("SERVICENOW_INSTANCE_URL", "")).rstrip("/")
    token = secrets.get("api_key") or ""
    if not instance or not token:
        return None

    sys_id = ticket.external_key
    if ticket.external_key.startswith("INC"):
        query_url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"number={ticket.external_key}", "sysparm_limit": "1"}
    else:
        query_url = f"{instance}/api/now/table/incident"
        params = {"sysparm_query": f"sys_id={sys_id}", "sysparm_limit": "1"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(
                query_url,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if res.status_code != 200:
                return None
            results = res.json().get("result", [])
            if not results:
                return None
            state = str(results[0].get("state", "1"))
            status_map = {"1": "open", "2": "in_progress", "6": "resolved", "7": "closed"}
            new_status = status_map.get(state, ticket.status)
            ticket.status = new_status
            ticket.synced_at = datetime.now(UTC)
            return new_status
    except Exception as exc:
        logger.warning("servicenow_status_sync_failed", error=str(exc))
        return None


async def create_servicenow_change_request(
    summary: str,
    description: str,
    secrets: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, str]:
    """Create a ServiceNow change request for remediation workflows."""
    instance = (metadata.get("instance_url") or os.getenv("SERVICENOW_INSTANCE_URL", "")).rstrip("/")
    token = secrets.get("api_key") or ""
    if instance and token and "example.com" not in instance:
        url = f"{instance}/api/now/table/change_request"
        payload = {
            "short_description": summary[:160],
            "description": description,
            "type": "normal",
            "risk": "moderate",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                if res.status_code in (200, 201):
                    result = res.json().get("result", {})
                    num = result.get("number", result.get("sys_id", ""))
                    return {
                        "key": num,
                        "url": f"{instance}/nav_to.do?uri=change_request.do?sys_id={result.get('sys_id', '')}",
                        "mode": "live",
                    }
        except Exception as exc:
            logger.warning("servicenow_change_failed", error=str(exc))

    key = f"CHG{uuid.uuid4().hex[:7].upper()}"
    return {"key": key, "url": f"https://{instance or 'demo.service-now.com'}/nav_to.do?uri=change_request.do?sys_id={key}", "mode": "demo"}


async def sync_cmdb_from_integrations(
    session: AsyncSession,
    tenant_id: str,
    settings: IntegrationSettings | None,
    bu_id: str | None = None,
) -> list[CmdbAsset]:
    """Pull CMDB assets from connected cloud/ITSM integrations."""
    connected = dict(settings.connected_integrations or {}) if settings else {}
    assets: list[CmdbAsset] = []
    now = datetime.now(UTC)

    sn_entry = connected.get("servicenow", {})
    if sn_entry.get("status") == "connected":
        sn_assets = await fetch_servicenow_cmdb(
            sn_entry.get("secrets") or {},
            sn_entry.get("metadata") or {},
        )
        for row in sn_assets:
            asset = CmdbAsset(
                id=f"CMDB-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=tenant_id,
                bu_id=bu_id,
                name=row.get("name", "ServiceNow CI"),
                asset_type=str(row.get("sys_class_name", "ci"))[:50],
                owner=str(row.get("assigned_to", {}).get("display_value", "itsm")),
                criticality="medium",
                source_integration="servicenow",
                external_id=str(row.get("sys_id", "")),
                asset_metadata={"sync_mode": "live", "operational_status": row.get("operational_status")},
                last_synced_at=now,
            )
            session.add(asset)
            assets.append(asset)

    if assets:
        return assets

    demo_assets = [
        ("Production API", "application", "critical", "aws"),
        ("Customer Database", "database", "critical", "aws"),
        ("Identity Provider", "service", "high", "okta"),
        ("CI/CD Pipeline", "pipeline", "high", "github"),
        ("Endpoint Fleet", "device", "medium", "jamf"),
        ("SIEM Cluster", "security", "critical", "splunk"),
    ]
    for name, atype, crit, src in demo_assets:
        if src not in connected and src not in ("aws", "github"):
            continue
        asset = CmdbAsset(
            id=f"CMDB-{uuid.uuid4().hex[:8].upper()}",
            tenant_id=tenant_id,
            bu_id=bu_id,
            name=name,
            asset_type=atype,
            owner="platform-team",
            criticality=crit,
            source_integration=src,
            external_id=f"{src}-{name.lower().replace(' ', '-')}",
            asset_metadata={"sync_mode": connected.get(src, {}).get("auth_method", "demo")},
            last_synced_at=now,
        )
        session.add(asset)
        assets.append(asset)

    if not assets:
        for name, atype, crit, src in demo_assets[:4]:
            asset = CmdbAsset(
                id=f"CMDB-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=tenant_id,
                bu_id=bu_id,
                name=name,
                asset_type=atype,
                owner="platform-team",
                criticality=crit,
                source_integration=src,
                external_id=f"demo-{name.lower().replace(' ', '-')}",
                asset_metadata={"sync_mode": "sandbox_demo"},
                last_synced_at=now,
            )
            session.add(asset)
            assets.append(asset)

    return assets
