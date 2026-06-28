"""Security Posture Timeline — Historical replay of security posture.

Visual timeline showing how the organization's security posture evolved
over time. Users can scrub backward and see RAG transitions, compliance
impacts, and metric trends. Essential for SOC2 Type II audit evidence.
"""
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import require_feature
from grc_dashboard.db.models import User
from grc_dashboard.db.persistence import list_timeline, save_timeline_snapshot
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant
from grc_dashboard.timeline.events import demo_security_events

logger = structlog.get_logger(__name__)
router = APIRouter()

# In-memory timeline store (in production, this would be in the DB)
_timeline_store: list[dict[str, Any]] = []


def record_snapshot(metrics: list[dict[str, Any]], run_id: str) -> None:
    """Record a metric snapshot for timeline history."""
    snapshot = {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "metrics": [
            {
                "metric_id": m.get("metric_id"),
                "metric_name": m.get("metric_name"),
                "value": m.get("value"),
                "rag_status": m.get("rag_status"),
                "ale_usd": m.get("ale_usd", 0),
                "var_95_usd": m.get("var_95_usd", 0),
            }
            for m in metrics
        ],
        "summary": {
            "green": sum(1 for m in metrics if m.get("rag_status") == "Green"),
            "amber": sum(1 for m in metrics if m.get("rag_status") == "Amber"),
            "red": sum(1 for m in metrics if m.get("rag_status") == "Red"),
            "total_var_usd": sum(m.get("var_95_usd", 0) for m in metrics),
        },
    }
    _timeline_store.append(snapshot)
    # Keep last 500 snapshots
    if len(_timeline_store) > 500:
        _timeline_store.pop(0)


def _generate_historical_data() -> list[dict[str, Any]]:
    """Generate 90 days of historical data for demo/first-run scenarios."""
    random.seed(12345)
    history = []
    now = datetime.now(UTC)

    # Base values that evolve over time
    base = {
        "KRI-MTTD-001": {"name": "Mean Time to Detect (MTTD)", "start": 22.0, "end": 14.2, "unit": "minutes"},
        "KRI-MTTR-001": {"name": "Mean Time to Respond (MTTR)", "start": 38.0, "end": 48.7, "unit": "minutes"},
        "KPI-FPR-001":  {"name": "False Positive Rate (FPR)", "start": 28.0, "end": 18.4, "unit": "%"},
        "KRI-CVE-001":  {"name": "Critical CVE Patch Lag", "start": 4.0, "end": 8.0, "unit": "days"},
        "KPI-PHI-001":  {"name": "Privileged Access Reviews", "start": 82.0, "end": 94.1, "unit": "%"},
        "KRI-DLP-001":  {"name": "DLP Policy Violations", "start": 22.0, "end": 37.0, "unit": "incidents"},
    }

    for day in range(90, -1, -1):
        ts = now - timedelta(days=day)
        progress = (90 - day) / 90.0
        metrics_snapshot = []

        for mid, cfg in base.items():
            # Linear interpolation with noise
            val = cfg["start"] + (cfg["end"] - cfg["start"]) * progress
            noise = random.gauss(0, abs(cfg["end"] - cfg["start"]) * 0.08)
            val = max(0, round(val + noise, 1))

            # Events: simulate a security incident at day 45
            if 42 <= day <= 50 and mid in ("KRI-MTTD-001", "KRI-MTTR-001"):
                val *= random.uniform(1.3, 1.8)
                val = round(val, 1)

            # RAG classification
            rag_thresholds = {
                "KRI-MTTD-001": (10, 20), "KRI-MTTR-001": (30, 60),
                "KPI-FPR-001": (25, 40), "KRI-CVE-001": (3, 7),
                "KRI-DLP-001": (15, 30),
            }
            if mid == "KPI-PHI-001":
                rag = "Green" if val >= 90 else "Amber" if val >= 80 else "Red"
            elif mid in rag_thresholds:
                g, a = rag_thresholds[mid]
                rag = "Green" if val <= g else "Amber" if val <= a else "Red"
            else:
                rag = "Amber"

            ale = int(val * random.uniform(8000, 15000))
            metrics_snapshot.append({
                "metric_id": mid,
                "metric_name": cfg["name"],
                "value": val,
                "unit": cfg["unit"],
                "rag_status": rag,
                "ale_usd": ale,
                "var_95_usd": int(ale * random.uniform(2.0, 3.5)),
            })

        history.append({
            "timestamp": ts.isoformat(),
            "run_id": f"HIST_{ts.strftime('%Y%m%d')}",
            "metrics": metrics_snapshot,
            "summary": {
                "green": sum(1 for m in metrics_snapshot if m["rag_status"] == "Green"),
                "amber": sum(1 for m in metrics_snapshot if m["rag_status"] == "Amber"),
                "red": sum(1 for m in metrics_snapshot if m["rag_status"] == "Red"),
                "total_var_usd": sum(m["var_95_usd"] for m in metrics_snapshot),
            },
        })

    return history


@router.get("/")
async def get_timeline(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=90, ge=1, le=365),
    metric_id: str = Query(default=None),
    current_user: User = Depends(require_feature("timeline")),
) -> dict[str, Any]:
    """Return security posture timeline from persisted snapshots."""
    tenant_id = get_tenant_id(request)
    raw = await list_timeline(db, tenant_id, days)
    filtered = [
        {
            "timestamp": snap["snapshot_at"],
            "run_id": f"HIST_{snap['snapshot_at'][:10].replace('-', '')}",
            "metrics": snap["metrics"],
            "summary": {
                **snap["summary"],
                "total_var_usd": sum(m.get("var_95_usd", 0) for m in snap.get("metrics", [])),
            },
        }
        for snap in raw
    ]

    # If metric_id specified, extract that metric's trend
    metric_trend = None
    if metric_id:
        metric_trend = []
        for snap in filtered:
            for m in snap.get("metrics", []):
                if m["metric_id"] == metric_id:
                    metric_trend.append({
                        "timestamp": snap["timestamp"],
                        "value": m["value"],
                        "rag_status": m["rag_status"],
                        "ale_usd": m.get("ale_usd", 0),
                        "var_95_usd": m.get("var_95_usd", 0),
                    })
                    break

    # Detect RAG transitions (state changes)
    rag_events = []
    prev_rags: dict[str, str] = {}
    for snap in filtered:
        for m in snap.get("metrics", []):
            mid = m["metric_id"]
            rag = m["rag_status"]
            if mid in prev_rags and prev_rags[mid] != rag:
                rag_events.append({
                    "timestamp": snap["timestamp"],
                    "metric_id": mid,
                    "metric_name": m.get("metric_name", mid),
                    "from_rag": prev_rags[mid],
                    "to_rag": rag,
                    "severity": "critical" if rag == "Red" else "warning" if rag == "Amber" else "recovery",
                })
            prev_rags[mid] = rag

    # Calculate improvement trends
    if len(filtered) >= 2:
        first = filtered[0]
        last = filtered[-1]
        posture_change = {
            "period_start": first["timestamp"],
            "period_end": last["timestamp"],
            "var_change_usd": last["summary"]["total_var_usd"] - first["summary"]["total_var_usd"],
            "var_change_pct": round(
                ((last["summary"]["total_var_usd"] - first["summary"]["total_var_usd"])
                 / max(1, first["summary"]["total_var_usd"])) * 100, 1
            ),
            "rag_transitions": len(rag_events),
        }
    else:
        posture_change = None

    return {
        "period_days": days,
        "total_snapshots": len(filtered),
        "snapshots": filtered,
        "rag_events": rag_events,
        "metric_trend": metric_trend,
        "posture_change": posture_change,
    }


@router.get("/events")
async def get_security_events(
    request: Request,
    current_user: User = Depends(require_feature("timeline")),
) -> dict[str, Any]:
    """Return security events — demo storyline for sandboxes; empty for production until SIEM ingests."""
    tenant_id = get_tenant_id(request)
    if is_demo_tenant(tenant_id):
        events = demo_security_events()
        return {"events": events, "total": len(events), "source": "sandbox_scenario"}

    return {
        "events": [],
        "total": 0,
        "source": "live",
        "message": (
            "No timeline events yet. Events appear when your SIEM pipeline runs "
            "and records posture changes for your organization."
        ),
    }
