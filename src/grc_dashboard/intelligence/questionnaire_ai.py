"""AI-powered security questionnaire drafting at scale."""
from __future__ import annotations

from typing import Any

from grc_dashboard.intelligence.llm_client import complete_prompt

QUESTIONNAIRE_LIBRARY: dict[str, dict[str, Any]] = {
    "sig_lite": {
        "name": "SIG Lite",
        "version": "2024.1",
        "question_count": 120,
        "description": "Standardized Information Gathering — vendor due diligence",
    },
    "caiq": {
        "name": "CAIQ (CSA)",
        "version": "4.0",
        "question_count": 261,
        "description": "Cloud Security Alliance consensus assessment",
    },
    "soc2_readiness": {
        "name": "SOC 2 Readiness",
        "version": "TSC 2022",
        "question_count": 64,
        "description": "Trust Services Criteria pre-audit questionnaire",
    },
    "iso27001": {
        "name": "ISO 27001 Annex A",
        "version": "2022",
        "question_count": 93,
        "description": "ISMS control self-assessment",
    },
    "nist_csf": {
        "name": "NIST CSF 2.0",
        "version": "2.0",
        "question_count": 48,
        "description": "Cybersecurity framework maturity assessment",
    },
    "hipaa": {
        "name": "HIPAA Security Rule",
        "version": "2024",
        "question_count": 54,
        "description": "PHI safeguards and BAA readiness",
    },
    "pci_dss": {
        "name": "PCI DSS v4.0",
        "version": "4.0",
        "question_count": 78,
        "description": "Cardholder data environment controls",
    },
    "custom_rfp": {
        "name": "Enterprise Security RFP",
        "version": "1.0",
        "question_count": 200,
        "description": "Large enterprise procurement security questionnaire",
    },
}


def _deterministic_answer(question: str, context: dict[str, Any]) -> str:
    q = question.lower()
    metrics = context.get("metrics_summary", "")
    readiness = context.get("readiness_pct", "")
    if "encrypt" in q:
        return "Yes — AES-256 at rest and TLS 1.2+ in transit for all production systems."
    if "mfa" in q or "multi-factor" in q:
        return "Yes — MFA enforced for all workforce and privileged accounts via IdP policy."
    if "incident" in q or "mttd" in q or "mttr" in q:
        return f"Yes — documented IR program. {metrics}"
    if "penetration" in q or "pen test" in q:
        return "Annual third-party penetration test; findings tracked in remediation workflow."
    if "soc 2" in q or "soc2" in q:
        return f"SOC 2 TSC controls monitored continuously. Current readiness: {readiness}%."
    if "vendor" in q or "third" in q:
        return "Third-party risk managed via SENTINEL scoring, SIG questionnaires, and breach monitoring."
    return (
        "Controls are documented, monitored via continuous control monitoring, "
        "and evidenced in the SHA-256 linked evidence vault."
    )


async def draft_questionnaire_answers(
    template_id: str,
    questions: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Draft answers for a questionnaire — AI when configured, deterministic fallback."""
    tpl = QUESTIONNAIRE_LIBRARY.get(template_id, QUESTIONNAIRE_LIBRARY["sig_lite"])
    answers: dict[str, str] = {}
    sources: dict[str, str] = {}
    ai_used = 0

    batch_prompt_parts = []
    for q in questions[:50]:
        qid = q.get("id", q.get("question_id", ""))
        text = q.get("text", q.get("question", ""))
        if not qid or not text:
            continue

        if use_ai and len(batch_prompt_parts) < 8:
            batch_prompt_parts.append(f"- [{qid}] {text}")

        answer = _deterministic_answer(text, context)
        answers[qid] = answer
        sources[qid] = "deterministic"

    if use_ai and batch_prompt_parts:
        prompt = (
            f"Draft concise security questionnaire answers for {tpl['name']}. "
            f"Context: {context.get('company_name', 'Organization')}. "
            f"Metrics: {context.get('metrics_summary', '')}. "
            f"Readiness: {context.get('readiness_pct', '')}%.\n\n"
            "Answer each question in format [ID]: answer (2-3 sentences, auditor-ready).\n\n"
            + "\n".join(batch_prompt_parts)
        )
        text, source = await complete_prompt(prompt)
        if text and source != "unavailable":
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("[") and "]:" in line:
                    qid, ans = line.split("]:", 1)
                    qid = qid.strip("[]- ")
                    if qid in answers:
                        answers[qid] = ans.strip()
                        sources[qid] = source
                        ai_used += 1

    for q in questions[50:]:
        qid = q.get("id", q.get("question_id", ""))
        text = q.get("text", q.get("question", ""))
        if qid and text and qid not in answers:
            answers[qid] = _deterministic_answer(text, context)
            sources[qid] = "deterministic"

    return {
        "template_id": template_id,
        "template_name": tpl["name"],
        "answers": answers,
        "sources": sources,
        "ai_drafted_count": ai_used,
        "total_answered": len(answers),
        "ai_available": ai_used > 0 or bool(context.get("llm_configured")),
    }
