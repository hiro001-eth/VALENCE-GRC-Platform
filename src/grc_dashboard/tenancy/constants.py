"""Tenant identifiers and demo account configuration."""

DEMO_TENANT_IDS: frozenset[str] = frozenset({
    "demo-global-hq",
    "demo-us-retail",
    "demo-eu-fintech",
    "demo-healthcare",
})

DEMO_USERNAMES: frozenset[str] = frozenset({
    "admin",
    "ciso",
    "analyst",
    "auditor",
})

# Backward-compatible aliases from earlier builds
LEGACY_TENANT_ALIASES: dict[str, str] = {
    "default": "demo-global-hq",
    "us-retail": "demo-us-retail",
    "eu-fintech": "demo-eu-fintech",
    "acme_retail": "demo-us-retail",
    "acme_fintech": "demo-eu-fintech",
}


def normalize_tenant_id(tenant_id: str) -> str:
    return LEGACY_TENANT_ALIASES.get(tenant_id, tenant_id)


def is_demo_tenant(tenant_id: str) -> bool:
    return normalize_tenant_id(tenant_id) in DEMO_TENANT_IDS


def is_demo_username(username: str) -> bool:
    return username in DEMO_USERNAMES
