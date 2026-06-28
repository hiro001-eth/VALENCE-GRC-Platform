from typing import Any
import structlog

from grc_dashboard.config import Settings
from grc_dashboard.models.metric import MetricDefinition, MetricValue
from grc_dashboard.models.rag import RAGAssignment, TrendDelta

logger = structlog.get_logger(__name__)

class NarrativeEngine:
    """
    Tier-0 AI Narrative Generator.
    Synthesizes numerical telemetry, FAIR risk, and predictive trends into a 
    board-ready 3-sentence narrative. Falls back to deterministic templating
    if the AI endpoint is unreachable to prevent pipeline failure.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        # In production, this would be an Azure OpenAI or local Ollama URL
        self.llm_api_url = "https://api.internal.ai/v1/completions"

    async def generate_narrative(
        self, 
        definition: MetricDefinition, 
        metric: MetricValue, 
        rag: RAGAssignment, 
        trend: TrendDelta | None
    ) -> str:
        
        # Build the prompt context
        self._build_context(definition, metric, rag, trend)
        
        try:
            # Attempt to generate via LLM (Mocked for boilerplate)
            # return await self._call_llm(context)
            
            # For boilerplate execution, we immediately fallback to the deterministic generator
            return self._deterministic_fallback(definition, metric, rag, trend)
        except Exception as e:
            logger.warning("llm_narrative_failed_using_fallback", error=str(e))
            return self._deterministic_fallback(definition, metric, rag, trend)

    def _build_context(self, d: MetricDefinition, m: MetricValue, r: RAGAssignment, t: TrendDelta | None) -> dict[str, Any]:
        return {
            "metric_name": d.metric_name,
            "current_value": m.value,
            "status": r.rag_status,
            "financial_risk_usd": r.annualized_loss_expectancy_usd,
            "trend": t.delta_direction if t else "flat",
            "predictive_breach": t.predictive_breach_days if t else None
        }

    def _deterministic_fallback(self, d: MetricDefinition, m: MetricValue, r: RAGAssignment, t: TrendDelta | None) -> str:
        """Rule-based fallback ensuring strict 3-sentence structure."""
        # Sentence 1: Status and Value
        s1 = f"The '{d.metric_name}' is currently operating at {m.value} {d.unit}, maintaining a '{r.rag_status}' status posture."
        
        # Sentence 2: Trend & Prediction
        s2 = "Data trends indicate stable performance with no immediate breach forecasted."
        if t:
            if t.predictive_breach_days:
                s2 = f"However, predictive forecasting indicates a mathematical certainty of breaching critical thresholds within {t.predictive_breach_days} days if current trajectory holds."
            elif t.significance:
                s2 = f"We have detected a statistically significant {t.delta_direction}ward trend of {t.delta_percent:.1f}% compared to the historical baseline."

        # Sentence 3: Financial & Compliance Risk
        s3 = "Compliance mappings are actively maintained."
        if r.annualized_loss_expectancy_usd > 0:
            s3 = f"At this operational level, the annualized Value-at-Risk (VaR) exposure is estimated at ${r.annualized_loss_expectancy_usd:,.2f} USD."

        return f"{s1} {s2} {s3}"
