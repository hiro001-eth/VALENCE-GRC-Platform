
import os
import structlog

import httpx

from grc_dashboard.config import Settings
from grc_dashboard.models.metric import MetricDefinition
from grc_dashboard.models.rag import RAGAssignment, TrendDelta

logger = structlog.get_logger(__name__)

class ITSMOrchestrator:
    """
    Tier-0 Closed-Loop GRC Orchestrator.
    Creates Jira tickets when thresholds are breached or predicted to breach.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.itsm_api_url = os.getenv("JIRA_URL", "https://jira.internal.corp/rest/api/2/issue")
        self.project_key = os.getenv("JIRA_PROJECT_KEY", "SECCOMP")
        self.jira_email = os.getenv("JIRA_EMAIL", "")
        self.jira_api_token = os.getenv("JIRA_API_TOKEN", "")

    async def evaluate_and_enforce(
        self, 
        definition: MetricDefinition, 
        rag: RAGAssignment, 
        trend: TrendDelta | None,
        narrative: str
    ) -> str | None:
        needs_ticket = False
        priority = "Medium"
        
        if rag.rag_status == "Red":
            needs_ticket = True
            priority = "Highest"
        elif trend and trend.predictive_breach_days and trend.predictive_breach_days <= 14:
            needs_ticket = True
            priority = "High"
            
        if not needs_ticket:
            return None

        return await self._dispatch_ticket(definition, rag, priority, narrative)

    async def _dispatch_ticket(self, definition: MetricDefinition, rag: RAGAssignment, priority: str, narrative: str) -> str:
        summary = f"[VALENCE] {definition.metric_id} — {rag.rag_status} threshold breach"
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": narrative,
                "issuetype": {"name": "Task"},
                "priority": {"name": priority},
            }
        }

        if self.jira_api_token and self.jira_email and "internal.corp" not in self.itsm_api_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(
                        self.itsm_api_url,
                        json=payload,
                        auth=(self.jira_email, self.jira_api_token),
                        headers={"Accept": "application/json"},
                    )
                    if res.status_code in (200, 201):
                        ticket_key = res.json().get("key", "")
                        logger.info("jira_ticket_created", ticket_id=ticket_key, metric_id=definition.metric_id)
                        return ticket_key
            except Exception as exc:
                logger.warning("jira_dispatch_failed", error=str(exc))

        ticket_id = f"{self.project_key}-AUTO-{rag.metric_id[-4:]}"
        logger.warning(
            "itsm_ticket_dispatched",
            ticket_id=ticket_id,
            metric_id=definition.metric_id,
            assignee=definition.business_owner,
            priority=priority,
            mode="mock",
        )
        return ticket_id
