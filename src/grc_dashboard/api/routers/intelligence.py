"""AI root-cause explainer — plain-English metric analysis."""
from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from grc_dashboard.api.tenant_context import get_tenant_id, get_tenant_results
from grc_dashboard.auth.dependencies import RequireAnalyst
from grc_dashboard.compliance.framework_loader import FrameworkLoader
from grc_dashboard.compliance.gap_analyzer import ComplianceGapAnalyzer
from grc_dashboard.db.models import MetricHistoryRecord, User
from grc_dashboard.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)
router = APIRouter()
_analyzer = ComplianceGapAnalyzer(FrameworkLoader())


def _build_explanation(
    metric: dict[str, Any],
    history: list[dict[str, Any]],
    related_controls: list[dict[str, str]],
) -> str:
    name = metric.get("metric_name", metric.get("metric_id", "Metric"))
    rag = metric.get("rag_status", "Unknown")
    value = metric.get("value", "—")
    ale = metric.get("ale_usd", 0)

    trend = "stable"
    if len(history) >= 2:
        prev = history[-2].get("value", 0)
        curr = history[-1].get("value", 0)
        if curr > prev * 1.05:
            trend = "worsening"
        elif curr < prev * 0.95:
            trend = "improving"

    lines = [
        f"**{name}** is **{rag}** this week (current value: {value}).",
    ]
    if trend == "worsening":
        lines.append("The trend is worsening compared to the previous pipeline run, which is the primary reason this metric moved into a higher-risk state.")
    elif trend == "improving":
        lines.append("The trend is improving versus the previous run, but the metric remains in a cautionary band due to threshold proximity.")
    else:
        lines.append("The value has remained relatively stable, but threshold rules still classify it as elevated risk.")

    if ale and ale > 0:
        lines.append(f"Financial exposure (ALE) is estimated at **${ale:,.0f}** annually at this operating level.")

    if related_controls:
        ctrl = ", ".join(f"{c['framework']} {c['control_id']}" for c in related_controls[:3])
        lines.append(f"This metric maps to compliance controls: {ctrl}. Auditors will expect evidence showing remediation progress on these controls.")

    if rag == "Red":
        lines.append("**Recommended action:** assign an owner, open a finding in the risk register, and attach remediation evidence within 48 hours.")
    elif rag == "Amber":
        lines.append("**Recommended action:** review SIEM detection rules and confirm patch/response SLAs before the next audit cycle.")

    return " ".join(lines)


async def _related_controls(metric_id: str, metrics: list[dict[str, Any]]) -> list[dict[str, str]]:
    related: list[dict[str, str]] = []
    for fw in FrameworkLoader().list_frameworks():
        analysis = _analyzer.analyze_gap(fw, metrics)
        for control in analysis.get("controls", []):
            if metric_id in control.get("metric_ids", []):
                related.append({
                    "framework": fw,
                    "control_id": control.get("control_id", ""),
                    "status": control.get("status", ""),
                })
    return related


async def _try_ollama_explain(base_url: str, metric: dict[str, Any], context: str) -> str | None:
    import httpx

    prompt = (
        f"Explain in 3-4 sentences for a CISO why this GRC metric is {metric.get('rag_status')}: "
        f"{metric.get('metric_name')} = {metric.get('value')}. Context: {context[:500]}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={"model": os.getenv("OLLAMA_MODEL", "llama3.2"), "prompt": prompt, "stream": False},
            )
            if res.status_code == 200:
                return res.json().get("response", "").strip() or None
    except Exception as exc:
        logger.warning("ollama_explain_failed", error=str(exc))
    return None


async def _try_openai_explain(api_key: str, metric: dict[str, Any], context: str) -> str | None:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {"role": "system", "content": "You are a GRC analyst. Be concise and actionable."},
                        {"role": "user", "content": f"Metric: {metric.get('metric_name')} ({metric.get('rag_status')}). {context[:600]}"},
                    ],
                    "max_tokens": 300,
                },
            )
            if res.status_code == 200:
                choices = res.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip() or None
    except Exception as exc:
        logger.warning("openai_explain_failed", error=str(exc))
    return None


@router.get("/explain/{metric_id}")
async def explain_metric(
    metric_id: str,
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Answer: 'Why is my MTTD red this week?' in plain English."""
    tenant_id = get_tenant_id(request)
    results = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])
    metric = next((m for m in metrics if m.get("metric_id") == metric_id), None)
    if not metric:
        raise HTTPException(status_code=404, detail=f"Metric '{metric_id}' not found in current run")

    history: list[dict[str, Any]] = []
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(MetricHistoryRecord)
            .where(
                MetricHistoryRecord.tenant_id == tenant_id,
                MetricHistoryRecord.metric_id == metric_id,
            )
            .order_by(MetricHistoryRecord.computed_at.desc())
            .limit(14)
        )
        history = [
            {"value": r.value, "rag_status": r.rag_status, "computed_at": r.computed_at.isoformat()}
            for r in reversed(rows.scalars().all())
        ]

    related = await _related_controls(metric_id, metrics)
    explanation = _build_explanation(metric, history, related)
    source = "deterministic"

    ollama_url = os.getenv("OLLAMA_URL")
    openai_key = os.getenv("OPENAI_API_KEY")
    if ollama_url:
        enhanced = await _try_ollama_explain(ollama_url, metric, explanation)
        if enhanced:
            explanation = enhanced
            source = "ollama"
    elif openai_key:
        enhanced = await _try_openai_explain(openai_key, metric, explanation)
        if enhanced:
            explanation = enhanced
            source = "openai"

    return {
        "metric_id": metric_id,
        "metric_name": metric.get("metric_name"),
        "rag_status": metric.get("rag_status"),
        "explanation": explanation,
        "explanation_plain": explanation.replace("**", ""),
        "related_controls": related,
        "history_points": len(history),
        "source": source,
    }


@router.get("/gaps")
async def prioritize_compliance_gaps(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """AI-ranked compliance gaps with remediation suggestions."""
    results = get_tenant_results(request)
    metrics: list[dict[str, Any]] = results.get("metrics", [])

    all_gaps: list[dict[str, Any]] = []
    for fw in FrameworkLoader().list_frameworks():
        analysis = _analyzer.analyze_gap(fw, metrics)
        for control in analysis.get("controls", []):
            status = control.get("status", "")
            if status in ("Non-Compliant", "At Risk"):
                priority = 100 if status == "Non-Compliant" else 60
                metric_ids = control.get("metric_ids", [])
                linked = [m for m in metrics if m.get("metric_id") in metric_ids]
                ale = max((m.get("ale_usd", 0) or 0) for m in linked) if linked else 0
                all_gaps.append({
                    "framework": fw,
                    "control_id": control.get("control_id"),
                    "title": control.get("title"),
                    "status": status,
                    "priority_score": priority + min(ale / 10000, 40),
                    "metric_ids": metric_ids,
                    "remediation": _suggest_remediation(control, linked),
                })

    all_gaps.sort(key=lambda g: g["priority_score"], reverse=True)

    summary = (
        f"Top priority: {all_gaps[0]['control_id']} ({all_gaps[0]['framework']}) — {all_gaps[0]['remediation']}"
        if all_gaps else "No open compliance gaps detected."
    )

    ollama_url = os.getenv("OLLAMA_URL")
    openai_key = os.getenv("OPENAI_API_KEY")
    source = "deterministic"
    if all_gaps and ollama_url:
        enhanced = await _try_ollama_explain(ollama_url, {"metric_name": "Compliance gaps", "rag_status": "Red", "value": len(all_gaps)}, summary)
        if enhanced:
            summary = enhanced
            source = "ollama"
    elif all_gaps and openai_key:
        enhanced = await _try_openai_explain(openai_key, {"metric_name": "Compliance gaps", "rag_status": "Red", "value": len(all_gaps)}, summary)
        if enhanced:
            summary = enhanced
            source = "openai"

    return {
        "total_gaps": len(all_gaps),
        "prioritized_gaps": all_gaps[:15],
        "executive_summary": summary,
        "source": source,
    }


def _suggest_remediation(control: dict[str, Any], metrics: list[dict[str, Any]]) -> str:
    cid = control.get("control_id", "")
    if "CC6" in cid or "AC" in cid or "PHI" in cid:
        return "Review privileged access logs, enforce MFA, and complete quarterly access review."
    if "CC7" in cid or "CVE" in cid or "MTTD" in str(control.get("metric_ids", [])):
        return "Tune SIEM detection rules, reduce MTTD, and patch critical CVEs within SLA."
    if "DLP" in cid or "GDPR" in cid or "HIPAA" in cid:
        return "Enable DLP policies, audit data flows, and verify encryption on sensitive stores."
    red_metrics = [m.get("metric_id") for m in metrics if m.get("rag_status") == "Red"]
    if red_metrics:
        return f"Remediate red metrics {', '.join(red_metrics[:3])} and attach evidence to vault."
    return "Assign control owner, open finding, and upload remediation evidence within 48 hours."


@router.post("/auto-remediate")
async def auto_remediate(
    request: Request,
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Autonomous agent: create findings + evidence requests for top compliance gaps."""
    from grc_dashboard.db.session import AsyncSessionLocal
    from grc_dashboard.intelligence.remediation_agent import auto_remediate_gaps

    tenant_id = get_tenant_id(request)
    metrics = get_tenant_results(request).get("metrics", [])
    async with AsyncSessionLocal() as session:
        return await auto_remediate_gaps(session, tenant_id, metrics, current_user.username)
