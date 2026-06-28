"""WebSocket router: authenticated real-time metric stream per tenant."""
from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from grc_dashboard.auth.jwt_handler import decode_token
from grc_dashboard.tenancy.constants import normalize_tenant_id
from grc_dashboard.tenancy.service import resolve_tenant_for_request

logger = structlog.get_logger(__name__)
router = APIRouter()


def _authenticate_ws(websocket: WebSocket) -> tuple[str, str]:
    token = websocket.query_params.get("token") or websocket.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        raise PermissionError("Authentication required")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise PermissionError("Invalid token type")
    username = payload.get("sub", "")
    tenant_id = payload.get("tenant_id", "demo-global-hq")
    if not username:
        raise PermissionError("Invalid token")
    return username, tenant_id


@router.websocket("/live")
async def websocket_live(websocket: WebSocket) -> None:
    """
    Authenticated WebSocket: streams metric updates for the user's resolved tenant.
    Connect with ``?token=<access_token>&tenant_id=<optional_demo_tenant>``.
    """
    try:
        username, home_tenant = _authenticate_ws(websocket)
        requested = websocket.query_params.get("tenant_id")
        tenant_id = resolve_tenant_for_request(
            jwt_tenant_id=home_tenant,
            jwt_username=username,
            requested_tenant_id=requested,
        )
        tenant_id = normalize_tenant_id(tenant_id)
    except Exception as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc))
        return

    await websocket.accept()
    clients: dict[Any, str] = websocket.app.state.websocket_clients
    clients[websocket] = tenant_id
    logger.info("websocket_client_connected", tenant_id=tenant_id, total_clients=len(clients))

    try:
        by_tenant: dict[str, Any] = websocket.app.state.latest_results_by_tenant
        latest = by_tenant.get(tenant_id, {})
        if latest:
            await websocket.send_text(json.dumps({"type": "metrics_update", "data": latest}))

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        logger.info("websocket_client_disconnected", tenant_id=tenant_id)
    finally:
        clients.pop(websocket, None)
