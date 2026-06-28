"""Integration credential helpers for cloud collectors."""
from __future__ import annotations

from typing import Any

SECRET_KEYS = frozenset({"api_key", "secret", "password", "token", "pat", "client_secret", "access_key", "secret_key"})


def extract_secrets(body: dict[str, Any]) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for key in SECRET_KEYS:
        if body.get(key):
            secrets[key] = str(body[key])
    if body.get("api_token"):
        secrets["api_key"] = str(body["api_token"])
    return secrets


def merge_collector_config(integration_config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = dict(integration_config.get("metadata") or {})
    secrets = dict(integration_config.get("secrets") or {})
    return metadata, secrets


def redact_integration_config(connected: dict[str, Any] | None) -> dict[str, Any]:
    if not connected:
        return {}
    safe: dict[str, Any] = {}
    for iid, cfg in connected.items():
        if not isinstance(cfg, dict):
            continue
        entry = {k: v for k, v in cfg.items() if k != "secrets"}
        entry["secrets_configured"] = bool(cfg.get("secrets"))
        safe[iid] = entry
    return safe
