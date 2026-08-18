"""Orchestrate cloud/identity evidence collection per tenant."""
from __future__ import annotations

from typing import Any

import structlog

from grc_dashboard.collectors.aws_collector import collect_aws_evidence
from grc_dashboard.collectors.azure_collector import collect_azure_evidence
from grc_dashboard.collectors.gcp_collector import collect_gcp_evidence
from grc_dashboard.collectors.github_collector import collect_github_evidence
from grc_dashboard.collectors.google_workspace_collector import collect_google_workspace_evidence
from grc_dashboard.collectors.jamf_collector import collect_jamf_evidence
from grc_dashboard.collectors.jira_collector import collect_jira_evidence
from grc_dashboard.collectors.kandji_collector import collect_kandji_evidence
from grc_dashboard.collectors.okta_collector import collect_okta_evidence
from grc_dashboard.collectors.servicenow_collector import collect_servicenow_evidence
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import AsyncSessionLocal
from grc_dashboard.integrations.secrets import merge_collector_config

logger = structlog.get_logger(__name__)

_COLLECTORS = {
    "aws": collect_aws_evidence,
    "gcp": collect_gcp_evidence,
    "github": collect_github_evidence,
    "google_workspace": collect_google_workspace_evidence,
    "okta": collect_okta_evidence,
    "azure": collect_azure_evidence,
    "jamf": collect_jamf_evidence,
    "kandji": collect_kandji_evidence,
    "jira": collect_jira_evidence,
    "servicenow": collect_servicenow_evidence,
}


async def run_cloud_collectors(
    tenant_id: str,
    run_id: str,
    connected_integrations: dict[str, Any] | None,
) -> int:
    """Pull read-only evidence from connected cloud integrations."""
    if not connected_integrations:
        return 0

    recorded = 0
    async with AsyncSessionLocal() as session:
        for integration_id, config in connected_integrations.items():
            if config.get("status") != "connected":
                continue
            collector = _COLLECTORS.get(integration_id)
            if not collector:
                continue
            metadata, secrets = merge_collector_config(config)
            try:
                items = await collector(tenant_id, metadata, secrets)
                for item in items:
                    await append_evidence_record(
                        session,
                        tenant_id,
                        event_type=item.get("event_type", "cloud_snapshot"),
                        category="cloud_evidence",
                        data=item.get("data", {}),
                        run_id=run_id,
                    )
                    recorded += 1
            except Exception as exc:
                logger.warning(
                    "cloud_collector_failed",
                    tenant_id=tenant_id,
                    integration=integration_id,
                    error=str(exc),
                )
    if recorded:
        logger.info("cloud_evidence_collected", tenant_id=tenant_id, count=recorded)
    return recorded
