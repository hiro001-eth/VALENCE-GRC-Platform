"""SENTINEL — third-party vendor risk scoring engine."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

CLASSIFICATION_WEIGHT = {"public": 10, "internal": 30, "confidential": 60, "restricted": 90}
TIER_WEIGHT = {"low": 10, "operational": 25, "strategic": 40}


def score_vendor(
    questionnaire_score: float,
    data_classification: str,
    incident_count: int,
    contract_sla_score: float,
    tier: str = "operational",
) -> dict[str, Any]:
    """Weighted vendor risk score (0–100, higher = riskier)."""
    q_risk = max(0.0, 100.0 - questionnaire_score) * 0.4
    data_risk = CLASSIFICATION_WEIGHT.get(data_classification.lower(), 30) * 0.3
    incident_risk = min(incident_count * 8, 40) * 0.2
    sla_risk = max(0.0, 100.0 - contract_sla_score) * 0.1
    tier_boost = TIER_WEIGHT.get(tier.lower(), 25) * 0.05

    risk_score = round(min(100.0, q_risk + data_risk + incident_risk + sla_risk + tier_boost), 1)
    if risk_score >= 75:
        risk_tier = "critical"
    elif risk_score >= 55:
        risk_tier = "high"
    elif risk_score >= 35:
        risk_tier = "medium"
    else:
        risk_tier = "low"

    return {
        "risk_score": risk_score,
        "risk_tier": risk_tier,
        "components": {
            "questionnaire": round(q_risk, 1),
            "data_classification": round(data_risk, 1),
            "incidents": round(incident_risk, 1),
            "contract_sla": round(sla_risk, 1),
            "tier_boost": round(tier_boost, 1),
        },
        "scored_at": datetime.now(UTC).isoformat(),
    }
