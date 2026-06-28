"""Live threat intelligence feeds — CISA KEV catalog and MITRE ATT&CK STIX."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

CISA_KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
_CACHE_DIR = Path("data/cache/threat_intel")
_KEV_CACHE = _CACHE_DIR / "cisa_kev.json"
_KEV_TTL_SECONDS = 3600

# High-impact techniques mapped to VALENCE metrics (enriched from MITRE ATT&CK STIX names)
_TECHNIQUE_METRIC_MAP: dict[str, list[str]] = {
    "T1566": ["KRI-MTTD-001", "KRI-DLP-001"],
    "T1486": ["KRI-MTTR-001"],
    "T1190": ["KRI-CVE-001"],
    "T1078": ["KPI-PHI-001"],
    "T1048": ["KRI-DLP-001"],
    "T1059": ["KRI-MTTD-001", "KRI-MTTR-001"],
    "T1210": ["KRI-CVE-001"],
}


async def fetch_cisa_kev_catalog() -> tuple[list[dict[str, Any]], str, bool]:
    """Return (vulnerabilities, last_sync_iso, from_live_feed)."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _KEV_CACHE.exists():
        age = datetime.now(UTC).timestamp() - _KEV_CACHE.stat().st_mtime
        if age < _KEV_TTL_SECONDS:
            data = json.loads(_KEV_CACHE.read_text(encoding="utf-8"))
            return _normalize_kev_entries(data.get("vulnerabilities", [])), data.get("dateReleased", ""), True

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(CISA_KEV_URL)
            response.raise_for_status()
            payload = response.json()
        _KEV_CACHE.write_text(json.dumps(payload), encoding="utf-8")
        released = payload.get("dateReleased", datetime.now(UTC).isoformat())
        entries = _normalize_kev_entries(payload.get("vulnerabilities", []))
        logger.info("cisa_kev_synced", count=len(entries), date_released=released)
        return entries, released, True
    except Exception as exc:
        logger.error("cisa_kev_fetch_failed", error=str(exc))
        if _KEV_CACHE.exists():
            data = json.loads(_KEV_CACHE.read_text(encoding="utf-8"))
            return _normalize_kev_entries(data.get("vulnerabilities", [])), data.get("dateReleased", ""), False
        return [], "", False


def _normalize_kev_entries(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize CISA JSON schema to VALENCE API shape; return most recent 50."""
    entries: list[dict[str, Any]] = []
    for item in raw[:50]:
        notes = item.get("notes", "") or item.get("shortDescription", "")
        ransomware = str(item.get("knownRansomwareCampaignUse", "Unknown")).lower()
        entries.append({
            "cve_id": item.get("cveID", ""),
            "vendor": item.get("vendorProject", item.get("vendor", "")),
            "product": item.get("product", ""),
            "vulnerability_name": item.get("vulnerabilityName", ""),
            "date_added": item.get("dateAdded", ""),
            "due_date": item.get("dueDate", ""),
            "severity": "CRITICAL",
            "cvss": 9.0,
            "known_ransomware_use": ransomware not in ("unknown", "no", "false"),
            "notes": notes[:500],
        })
    return entries


async def fetch_mitre_attack_trends() -> tuple[list[dict[str, Any]], str, bool]:
    """Derive technique intelligence from MITRE ATT&CK enterprise STIX bundle."""
    try:
        from grc_dashboard.config import get_settings
        from grc_dashboard.mitre.stix_loader import STIXLoader

        loader = STIXLoader(get_settings())
        bundle = await loader.load_enterprise_matrix()
        techniques = _extract_techniques_from_stix(bundle)
        return techniques, datetime.now(UTC).isoformat(), True
    except Exception as exc:
        logger.error("mitre_stix_fetch_failed", error=str(exc))
        return _fallback_mitre_trends(), datetime.now(UTC).isoformat(), False


def _extract_techniques_from_stix(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    objects = bundle.get("objects", [])
    attack_patterns = [
        obj for obj in objects
        if obj.get("type") == "attack-pattern" and not obj.get("revoked") and not obj.get("x_mitre_deprecated")
    ]
    prioritized_ids = set(_TECHNIQUE_METRIC_MAP.keys())
    trends: list[dict[str, Any]] = []

    for obj in attack_patterns:
        ext_refs = obj.get("external_references", [])
        technique_id = next(
            (ref.get("external_id", "") for ref in ext_refs if ref.get("source_name") == "mitre-attack"),
            "",
        )
        if technique_id not in prioritized_ids:
            continue
        name = obj.get("name", technique_id)
        tactics = [
            phase.get("phase_name", "").replace("-", " ").title()
            for phase in obj.get("kill_chain_phases", [])
            if phase.get("kill_chain_name") == "mitre-attack"
        ]
        trends.append({
            "technique_id": technique_id,
            "technique_name": name,
            "tactic": tactics[0] if tactics else "Multiple",
            "trend": "monitored",
            "change_pct": 0,
            "affected_metrics": _TECHNIQUE_METRIC_MAP.get(technique_id, []),
            "threat_groups": [],
            "description": (obj.get("description") or "")[:400],
            "source": "MITRE ATT&CK STIX 2.1",
        })
    return trends or _fallback_mitre_trends()


def _fallback_mitre_trends() -> list[dict[str, Any]]:
    return [
        {
            "technique_id": tid,
            "technique_name": name,
            "tactic": tactic,
            "trend": "monitored",
            "change_pct": 0,
            "affected_metrics": _TECHNIQUE_METRIC_MAP.get(tid, []),
            "threat_groups": [],
            "description": desc,
            "source": "MITRE ATT&CK (cached)",
        }
        for tid, name, tactic, desc in [
            ("T1566", "Phishing", "Initial Access", "Phishing remains a primary initial access vector per CISA/DBIR."),
            ("T1190", "Exploit Public-Facing Application", "Initial Access", "Edge device exploitation continues across sectors."),
            ("T1078", "Valid Accounts", "Persistence", "Stolen credentials and session hijacking."),
        ]
    ]


def correlate_threats(
    kev_feed: list[dict[str, Any]],
    mitre_trends: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    correlations: list[dict[str, Any]] = []
    metric_map = {m.get("metric_id"): m for m in metrics}
    cve_metric = metric_map.get("KRI-CVE-001", {})
    patch_lag = float(cve_metric.get("value", 0) or 0)
    kev_critical = [k for k in kev_feed if k.get("cvss", 0) >= 9.0]

    if patch_lag > 3 and kev_critical:
        correlations.append({
            "severity": "critical",
            "type": "kev_exposure",
            "title": f"{len(kev_critical)} CISA KEV critical CVEs while patch lag is {patch_lag} days",
            "description": (
                f"Live CISA KEV catalog lists {len(kev_critical)} critical actively exploited CVEs. "
                f"Your patch lag is {patch_lag} days."
            ),
            "affected_metrics": ["KRI-CVE-001"],
            "recommended_action": "Initiate emergency patch cycle for CISA KEV-listed vulnerabilities.",
            "estimated_risk_usd": len(kev_critical) * 100_000,
        })

    for technique in mitre_trends:
        for affected_mid in technique.get("affected_metrics", []):
            m = metric_map.get(affected_mid, {})
            if m.get("rag_status") in ("Amber", "Red"):
                correlations.append({
                    "severity": "high",
                    "type": "attack_trend",
                    "title": f"{technique['technique_name']} ({technique['technique_id']}) — {affected_mid} is {m.get('rag_status')}",
                    "description": technique.get("description", ""),
                    "affected_metrics": [affected_mid],
                    "threat_groups": technique.get("threat_groups", []),
                    "recommended_action": f"Review controls for {technique['technique_id']}.",
                })
    return correlations
