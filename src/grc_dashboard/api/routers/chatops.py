"""ChatOps assistant endpoints for Slack/Teams bots."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.db.models import User
from grc_dashboard.tenancy.constants import DEMO_TENANT_IDS, normalize_tenant_id
from grc_dashboard.tenancy.demo_scenarios import build_pipeline_error_state, build_tenant_metrics

logger = structlog.get_logger(__name__)
router = APIRouter()

_SLACK_MAX_AGE_SEC = 60 * 5


class ChatQuery(BaseModel):
    query: str


class TeamsMessage(BaseModel):
    text: str
    tenant_id: str | None = None


def _webhook_dev_mode() -> bool:
    return os.getenv("CHATOPS_WEBHOOK_DEV_MODE", "true").lower() in {"1", "true", "yes"}


def _default_webhook_tenant() -> str:
    fallback = "demo-global-hq"
    if DEMO_TENANT_IDS:
        fallback = sorted(DEMO_TENANT_IDS)[0]
    return normalize_tenant_id(os.getenv("CHATOPS_DEFAULT_TENANT_ID", fallback))


def _resolve_webhook_tenant(team_id: str | None = None) -> str:
    raw_map = os.getenv("CHATOPS_SLACK_TEAM_MAP", "").strip()
    if team_id and raw_map:
        try:
            mapping = json.loads(raw_map)
            if team_id in mapping:
                return normalize_tenant_id(str(mapping[team_id]))
        except json.JSONDecodeError:
            logger.warning("chatops_invalid_slack_team_map")
    return _default_webhook_tenant()


def _tenant_results(request: Request, tenant_id: str) -> dict[str, Any]:
    by_tenant: dict[str, Any] = getattr(request.app.state, "latest_results_by_tenant", {})
    if tenant_id in by_tenant:
        return by_tenant[tenant_id]
    from grc_dashboard.tenancy.constants import is_demo_tenant

    if is_demo_tenant(tenant_id):
        return build_tenant_metrics(tenant_id)
    return build_pipeline_error_state(tenant_id, "CHATOPS", "No metrics loaded for tenant")


def _build_answer(query: str, metrics: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    q = query.lower().strip()
    red = [m for m in metrics if m.get("rag_status") == "Red"]
    amber = [m for m in metrics if m.get("rag_status") == "Amber"]
    top_ale = sorted(metrics, key=lambda x: x.get("ale_usd") or 0, reverse=True)[:3]

    if any(k in q for k in ("compliance", "readiness", "score")):
        text = (
            f"Compliance posture: {summary.get('overall_rag', '—')} "
            f"with {len(red)} red and {len(amber)} amber metrics."
        )
    elif any(k in q for k in ("risk", "ale", "exposure")):
        top = ", ".join(
            f"{m.get('metric_name', m.get('metric_id'))} (${int(m.get('ale_usd') or 0):,})"
            for m in top_ale
        ) or "No risk metrics loaded yet."
        text = f"Top financial exposure drivers: {top}."
    elif any(k in q for k in ("incident", "red", "urgent")):
        if red:
            top = ", ".join(m.get("metric_name", m.get("metric_id", "unknown")) for m in red[:5])
            text = f"Urgent red metrics: {top}. Recommend remediation + ITSM sync."
        else:
            text = "No red metrics currently. Monitoring posture is within thresholds."
    elif any(k in q for k in ("help", "commands", "what can")):
        text = (
            "Ask me about: compliance score, top risk/ALE exposure, or urgent red metrics. "
            "Examples: `/valence compliance` · `/valence risk` · `/valence red metrics`"
        )
    else:
        text = (
            "I can answer compliance readiness, top risk exposure (ALE), and urgent red metrics. "
            "Try: `compliance score` or `top risk`."
        )

    return {
        "answer": text,
        "summary": {
            "overall_rag": summary.get("overall_rag", "—"),
            "total_ale_usd": summary.get("total_ale_usd", 0),
            "red_metrics": len(red),
            "amber_metrics": len(amber),
        },
    }


def _verify_slack_signature(
    signing_secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
) -> None:
    if not signing_secret:
        if _webhook_dev_mode():
            return
        raise HTTPException(status_code=503, detail="SLACK_SIGNING_SECRET not configured")

    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing Slack signature headers")

    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Slack timestamp") from exc

    if abs(time.time() - ts) > _SLACK_MAX_AGE_SEC:
        raise HTTPException(status_code=401, detail="Stale Slack request")

    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")


def _verify_teams_secret(provided: str | None) -> None:
    expected = os.getenv("CHATOPS_TEAMS_WEBHOOK_SECRET", "").strip()
    if not expected:
        if _webhook_dev_mode():
            return
        raise HTTPException(status_code=503, detail="CHATOPS_TEAMS_WEBHOOK_SECRET not configured")
    if not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid Teams webhook secret")


def _slack_response(answer: str, in_channel: bool = False) -> dict[str, Any]:
    return {
        "response_type": "in_channel" if in_channel else "ephemeral",
        "text": answer,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*VALENCE GRC*\n{answer}"},
            }
        ],
    }


def _teams_response(answer: str) -> dict[str, Any]:
    return {
        "type": "message",
        "text": answer,
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": "VALENCE GRC", "weight": "Bolder", "size": "Medium"},
                        {"type": "TextBlock", "text": answer, "wrap": True},
                    ],
                },
            }
        ],
    }


@router.get("/status")
async def chatops_status(request: Request, current_user: User = RequireAnalyst) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request) or {}
    metrics = results.get("metrics", [])
    summary = results.get("summary", {})
    red = sum(1 for m in metrics if m.get("rag_status") == "Red")
    return {
        "tenant_id": tenant_id,
        "ready": True,
        "metric_count": len(metrics),
        "red_metrics": red,
        "overall_rag": summary.get("overall_rag", "—"),
    }


@router.post("/query")
async def chatops_query(
    body: ChatQuery,
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request) or {}
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    summary = results.get("summary", {})
    payload = _build_answer(body.query, metrics, summary)
    return {"tenant_id": tenant_id, "query": body.query, **payload}


@router.post("/slack/command")
async def slack_slash_command(
    request: Request,
    x_slack_signature: str | None = Header(default=None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(default=None, alias="X-Slack-Request-Timestamp"),
) -> JSONResponse:
    """Slack slash command bridge — configure command `/valence` to this URL."""
    body = await request.body()
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    _verify_slack_signature(signing_secret, x_slack_request_timestamp, x_slack_signature, body)

    from urllib.parse import parse_qs

    form = parse_qs(body.decode("utf-8"))
    text = (form.get("text") or [""])[0].strip() or "help"
    team_id = (form.get("team_id") or [None])[0]
    tenant_id = _resolve_webhook_tenant(team_id)
    results = _tenant_results(request, tenant_id)
    payload = _build_answer(text, results.get("metrics", []), results.get("summary", {}))

    logger.info("chatops_slack_command", tenant_id=tenant_id, query=text[:80])
    return JSONResponse(_slack_response(payload["answer"]))


@router.post("/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: str | None = Header(default=None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(default=None, alias="X-Slack-Request-Timestamp"),
) -> JSONResponse:
    """Slack Events API — handles URL verification and app mentions."""
    body = await request.body()
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    _verify_slack_signature(signing_secret, x_slack_request_timestamp, x_slack_signature, body)

    try:
        event = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if event.get("type") == "url_verification":
        return JSONResponse({"challenge": event.get("challenge", "")})

    if event.get("type") == "event_callback":
        inner = event.get("event") or {}
        if inner.get("type") == "app_mention":
            text = (inner.get("text") or "").replace("<@", "").split(">", 1)[-1].strip() or "help"
            team_id = event.get("team_id")
            tenant_id = _resolve_webhook_tenant(team_id)
            results = _tenant_results(request, tenant_id)
            payload = _build_answer(text, results.get("metrics", []), results.get("summary", {}))
            return JSONResponse(_slack_response(payload["answer"], in_channel=True))

    return JSONResponse({"ok": True})


@router.post("/teams/message")
async def teams_message(
    request: Request,
    body: TeamsMessage,
    x_chatops_secret: str | None = Header(default=None, alias="X-ChatOps-Secret"),
) -> JSONResponse:
    """Microsoft Teams outgoing webhook / connector bridge."""
    _verify_teams_secret(x_chatops_secret)

    tenant_id = normalize_tenant_id(body.tenant_id or _default_webhook_tenant())
    results = _tenant_results(request, tenant_id)
    payload = _build_answer(body.text, results.get("metrics", []), results.get("summary", {}))

    logger.info("chatops_teams_message", tenant_id=tenant_id, query=body.text[:80])
    return JSONResponse(_teams_response(payload["answer"]))


@router.post("/teams/activity")
async def teams_bot_activity(
    request: Request,
    x_chatops_secret: str | None = Header(default=None, alias="X-ChatOps-Secret"),
) -> JSONResponse:
    """Teams Bot Framework activity payload (text field)."""
    _verify_teams_secret(x_chatops_secret)
    activity = await request.json()
    text = (activity.get("text") or "").strip()
    if not text:
        text = "help"
    tenant_id = _default_webhook_tenant()
    results = _tenant_results(request, tenant_id)
    payload = _build_answer(text, results.get("metrics", []), results.get("summary", {}))
    return JSONResponse(_teams_response(payload["answer"]))
