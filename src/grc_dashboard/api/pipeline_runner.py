"""Background pipeline runner — bridges GRC pipeline with per-tenant app state."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from grc_dashboard.pipeline.tenant_runner import (
    discover_production_tenant_ids,
    run_pipeline_for_tenant_safe,
)
from grc_dashboard.tenancy.constants import DEMO_TENANT_IDS
from grc_dashboard.tenancy.demo_scenarios import build_tenant_metrics

logger = structlog.get_logger(__name__)


class PipelineRunner:
    """Runs isolated pipelines per production tenant; demo tenants use curated scenarios."""

    async def run_once(self, state: Any) -> None:
        run_id = f"VALENCE_{uuid.uuid4().hex[:8].upper()}"
        logger.info("pipeline_run_start", run_id=run_id)

        by_tenant: dict[str, Any] = getattr(state, "latest_results_by_tenant", {})
        if not hasattr(state, "latest_results_by_tenant"):
            state.latest_results_by_tenant = by_tenant

        production_tenants = await discover_production_tenant_ids()
        for tenant_id in production_tenants:
            results = await run_pipeline_for_tenant_safe(tenant_id, run_id)
            by_tenant[tenant_id] = results
            if results.get("pipeline_status") == "ok":
                await self._persist_timeline(tenant_id, results, run_id)
                await self._record_evidence(tenant_id, results, run_id)
                await self._run_cerberus(tenant_id, results, run_id)
                await self._run_cloud_collectors(tenant_id, run_id)
            try:
                from grc_dashboard.alerting.alert_engine import AlertEngine

                alert_engine = AlertEngine()
                metrics = [{**m, "tenant_id": tenant_id} for m in results.get("metrics", [])]
                await alert_engine.process_metrics(run_id, metrics)
            except Exception as ae:
                logger.error("alert_processing_failed", run_id=run_id, tenant_id=tenant_id, error=str(ae))

        for demo_id in DEMO_TENANT_IDS:
            by_tenant[demo_id] = build_tenant_metrics(demo_id, run_id)
            await self._run_cloud_collectors(demo_id, run_id)

        state.last_run_at = datetime.now(UTC).isoformat()
        state.last_run_id = run_id
        await self._broadcast_all(state, by_tenant)
        logger.info("pipeline_run_complete", run_id=run_id, production_tenants=len(production_tenants))

    async def run_scheduled(self, state: Any, interval_seconds: int = 300) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await self.run_once(state)

    async def _persist_timeline(self, tenant_id: str, results: dict[str, Any], run_id: str) -> None:
        try:
            from grc_dashboard.db.persistence import save_timeline_snapshot
            from grc_dashboard.db.session import AsyncSessionLocal

            metrics = results.get("metrics", [])
            if not metrics:
                return
            async with AsyncSessionLocal() as session:
                await save_timeline_snapshot(session, tenant_id, metrics, run_id)
        except Exception as exc:
            logger.warning("timeline_snapshot_failed", tenant_id=tenant_id, error=str(exc))

    async def _record_evidence(self, tenant_id: str, results: dict[str, Any], run_id: str) -> None:
        try:
            from grc_dashboard.compliance.evidence_loop import record_pipeline_evidence

            metrics = results.get("metrics", [])
            if metrics:
                await record_pipeline_evidence(tenant_id, run_id, metrics)
        except Exception as exc:
            logger.warning("pipeline_evidence_failed", tenant_id=tenant_id, error=str(exc))

    async def _run_cerberus(self, tenant_id: str, results: dict[str, Any], run_id: str) -> None:
        try:
            from grc_dashboard.cerberus.pipeline import run_cerberus_pipeline

            metrics = results.get("metrics", [])
            if metrics:
                await run_cerberus_pipeline(tenant_id, run_id, metrics)
        except Exception as exc:
            logger.warning("cerberus_pipeline_failed", tenant_id=tenant_id, error=str(exc))

    async def _run_cloud_collectors(self, tenant_id: str, run_id: str) -> None:
        try:
            from grc_dashboard.collectors import run_cloud_collectors
            from grc_dashboard.pipeline.tenant_runner import load_integration_settings
            from grc_dashboard.tenancy.constants import is_demo_tenant

            integration = await load_integration_settings(tenant_id)
            connected = (integration.connected_integrations if integration else None) or {}
            if is_demo_tenant(tenant_id) and not connected:
                connected = {
                    "aws": {"status": "connected", "metadata": {"region": "us-east-1", "account_id": "123456789012"}},
                    "github": {"status": "connected", "metadata": {"org": "meridian-industries"}},
                    "google_workspace": {"status": "connected", "metadata": {"domain": "meridian.com"}},
                    "okta": {"status": "connected", "metadata": {"org_url": "https://meridian.okta.com"}},
                    "azure": {"status": "connected", "metadata": {"subscription_id": "sub-demo-001"}},
                    "gcp": {"status": "connected", "metadata": {"project_id": "meridian-prod"}},
                    "jamf": {"status": "connected", "metadata": {"url": "https://meridian.jamfcloud.com"}},
                    "kandji": {"status": "connected", "metadata": {"subdomain": "meridian"}},
                }
            if connected:
                await run_cloud_collectors(tenant_id, run_id, connected)
            await self._sync_personnel_and_vendors(tenant_id, connected)
        except Exception as exc:
            logger.warning("cloud_collectors_failed", tenant_id=tenant_id, error=str(exc))

    async def _sync_personnel_and_vendors(self, tenant_id: str, connected: dict[str, Any]) -> None:
        try:
            from grc_dashboard.db.session import AsyncSessionLocal
            from grc_dashboard.devices.mdm_sync import sync_mdm_devices
            from grc_dashboard.personnel.sync import sync_jml_from_integrations
            from grc_dashboard.vendor.breach_monitor import scan_vendor_breaches

            async with AsyncSessionLocal() as session:
                await sync_jml_from_integrations(session, tenant_id, connected)
                await sync_mdm_devices(session, tenant_id, connected)
                await scan_vendor_breaches(session, tenant_id)
        except Exception as exc:
            logger.warning("personnel_vendor_sync_failed", tenant_id=tenant_id, error=str(exc))

    async def _broadcast_all(self, state: Any, by_tenant: dict[str, Any]) -> None:
        import json

        clients: dict[Any, str] = getattr(state, "websocket_clients", {})
        if not clients:
            return

        disconnected: set[Any] = set()
        for ws, tenant_id in list(clients.items()):
            payload = by_tenant.get(tenant_id, {})
            if not payload:
                continue
            message = json.dumps({"type": "metrics_update", "data": payload})
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            clients.pop(ws, None)

    def _generate_tenant_demo_results(self, tenant_id: str, run_id: str = "VALENCE_DEMO") -> dict[str, Any]:
        from grc_dashboard.tenancy.constants import normalize_tenant_id

        return build_tenant_metrics(normalize_tenant_id(tenant_id), run_id)
