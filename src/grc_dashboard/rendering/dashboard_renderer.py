from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import DashboardRenderException
from grc_dashboard.models.dashboard import DashboardArtifact, DashboardCard
from grc_dashboard.models.metric import MetricValue
from grc_dashboard.models.mitre import CoverageMatrix
from grc_dashboard.models.rag import RAGAssignment, TrendDelta
from grc_dashboard.rendering.chart_builder import ChartBuilder

logger = structlog.get_logger(__name__)

class DashboardRenderer:
    """
    HTML dashboard generator via Jinja2 (ANCHOR:Q9).
    Produces single-page responsive layout.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chart_builder = ChartBuilder()
        # Fallback to local template if missing
        self.template_dir = Path("src/grc_dashboard/templates")
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_template_exists()
        self.env = Environment(loader=FileSystemLoader(self.template_dir))

    def render(
        self, 
        metrics: list[MetricValue], 
        rag_assignments: list[RAGAssignment], 
        trends: list[TrendDelta], 
        coverage: CoverageMatrix,
        run_id: str,
        snapshot_hash: str,
        narratives: dict[str, Any] | None = None, # map of metric_id to narrative string
        tickets: dict[str, Any] | None = None     # map of metric_id to ITSM ticket ID
    ) -> DashboardArtifact:
        try:
            narratives = narratives or {}
            tickets = tickets or {}
            cards = self._build_rag_cards(metrics, rag_assignments, trends, narratives, tickets)
            heatmap_json = self.chart_builder.build_mitre_heatmap(coverage)
            
            context = {
                "title": self.settings.dashboard.title,
                "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "run_id": run_id,
                "snapshot_hash": snapshot_hash,
                "cards": cards,
                "heatmap_json": heatmap_json,
                "overall_coverage": f"{coverage.overall_coverage * 100:.1f}%"
            }
            
            html_content = self._apply_template(context)
            
            output_dir = self.settings.dashboard.pdf_output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            
            html_path = output_dir / f"dashboard_{run_id}.html"
            self._write_html(html_content, html_path)
            
            return DashboardArtifact(
                artifact_id=f"art_{run_id}",
                html_path=html_path,
                pdf_path=output_dir / f"dashboard_{run_id}.pdf", # Resolved in PDF phase
                generated_at=datetime.now(UTC),
                metric_snapshot_hash=snapshot_hash,
                dashboard_run_id=run_id
            )
        except Exception as e:
            raise DashboardRenderException(
                message=f"HTML Rendering failed: {e}",
                correlation_id="none",
                stage_name="DashboardRender",
                dashboard_run_id=run_id
            ) from e

    def _build_rag_cards(
        self, 
        metrics: list[MetricValue], 
        rag_assignments: list[RAGAssignment], 
        trends: list[TrendDelta],
        narratives: dict[str, Any],
        tickets: dict[str, Any]
    ) -> list[DashboardCard]:
        rag_map = {r.metric_id: r for r in rag_assignments}
        trend_map = {t.metric_id: t for t in trends}
        
        cards = []
        for m in metrics:
            rag = rag_map.get(m.metric_id)
            trend = trend_map.get(m.metric_id)
            
            rag_status = rag.rag_status if rag else "NoData"
            gauge_json = self.chart_builder.build_gauge_chart(m.value, rag_status)
            
            cards.append(DashboardCard(
                metric_id=m.metric_id,
                title=f"{m.metric_id} Metric",
                value=f"{m.value:.2f}",
                rag_status=rag_status,
                trend_delta=trend,
                chart_data=[{"gauge": gauge_json}],
                executive_narrative=narratives.get(m.metric_id, "Narrative unavailable."),
                itsm_ticket_id=tickets.get(m.metric_id),
                financial_exposure_usd=rag.annualized_loss_expectancy_usd if rag else 0.0,
                var_95_usd=rag.var_95_usd if rag else 0.0,
                probability_of_breach=rag.probability_of_breach if rag else 0.0
            ))
        return cards

    def _apply_template(self, context: dict[str, Any]) -> str:
        template = self.env.get_template("dashboard.html")
        return template.render(**context)

    def _write_html(self, html: str, path: Path) -> Path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def _ensure_template_exists(self) -> None:
        """Creates a minimal boilerplate Jinja2 template if missing."""
        template_file = self.template_dir / "dashboard.html"
        if not template_file.exists():
            content = """
<!DOCTYPE html>
<html>
<head><title>{{ title }}</title><script src="https://cdn.plot.ly/plotly-latest.min.js"></script></head>
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f9fafb; color: #111827; margin: 2rem; }
    .card { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .status-badge { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-weight: bold; font-size: 0.875rem; }
    .status-Red { background: #fee2e2; color: #991b1b; }
    .status-Amber { background: #fef3c7; color: #92400e; }
    .status-Green { background: #d1fae5; color: #065f46; }
    .narrative { background: #f3f4f6; padding: 1rem; border-left: 4px solid #3b82f6; margin-top: 1rem; font-style: italic; }
    .ticket { margin-top: 0.5rem; font-size: 0.875rem; font-weight: bold; color: #dc2626; }
    .risk-box { margin: 0.75rem 0; font-size: 0.9rem; background: #eff6ff; padding: 0.75rem; border-radius: 6px; border: 1px dashed #bfdbfe; color: #1e40af; }
</style>
<body>
    <h1>{{ title }}</h1>
    <p><strong>Run ID:</strong> {{ run_id }} | <strong>Hash:</strong> {{ snapshot_hash }} | <strong>MITRE Coverage:</strong> {{ overall_coverage }}</p>
    <div style="display: grid; gap: 1.5rem;">
    {% for card in cards %}
        <div class="card">
            <h3>{{ card.title }}</h3>
            <p>Value: <strong>{{ card.value }}</strong> | Status: <span class="status-badge status-{{ card.rag_status }}">{{ card.rag_status }}</span></p>
            {% if card.financial_exposure_usd > 0 %}
            <div class="risk-box">
                📊 <strong>FAIR Quantitative Risk Analysis (Monte Carlo 1,000 Iterations):</strong><br>
                • Expected Loss Exposure (VaR): <strong>${{ card.financial_exposure_usd }}</strong> / year<br>
                • 95% Worst-Case Max Exposure: <strong>${{ card.var_95_usd }}</strong> / year<br>
                • Board Breach Probability (> $1M): <strong>{{ card.probability_of_breach * 100 }}%</strong>
            </div>
            {% endif %}
            <div class="narrative">
                <strong>Executive Summary:</strong><br>
                {{ card.executive_narrative }}
            </div>
            {% if card.itsm_ticket_id %}
            <div class="ticket">
                ⚠️ AUTO-REMEDIATION ENFORCED: Ticket {{ card.itsm_ticket_id }} created and assigned to Business Owner.
            </div>
            {% endif %}
        </div>
    {% endfor %}
    </div>
</body>
</html>
"""
            with open(template_file, "w", encoding="utf-8") as f:
                f.write(content)
