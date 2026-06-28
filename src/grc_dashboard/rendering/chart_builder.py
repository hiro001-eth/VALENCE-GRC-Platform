import json

import plotly.graph_objects as go
import plotly.utils

from grc_dashboard.models.metric import MetricValue
from grc_dashboard.models.mitre import CoverageMatrix


class ChartBuilder:
    """
    Plotly chart generator for dashboard visualizations.
    Returns JSON configs for embedded frontend rendering.
    """
    def build_trend_chart(self, metric_history: list[MetricValue]) -> str:
        if not metric_history:
            return "{}"
            
        x_dates = [m.computed_at.strftime("%Y-%m-%d") for m in metric_history]
        y_vals = [m.value for m in metric_history]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x_dates, y=y_vals,
            mode='lines+markers',
            line=dict(color='#3b82f6', width=2),
            marker=dict(size=6)
        ))
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=60,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False)
        )
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    def build_gauge_chart(self, value: float, rag_status: str) -> str:
        color = self._get_rag_color(rag_status)
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            gauge={
                'axis': {'range': [0, 100], 'visible': False},
                'bar': {'color': color},
                'bgcolor': "#f3f4f6",
                'borderwidth': 0,
            }
        ))
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=120,
            paper_bgcolor='rgba(0,0,0,0)',
        )
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    def build_mitre_heatmap(self, coverage_matrix: CoverageMatrix) -> str:
        # Simplified heatmap for boilerplate
        fig = go.Figure(data=go.Heatmap(
            z=[[0.1, 0.3, 0.5, 0.2], [0.8, 0.9, 0.1, 0.6]],
            x=['Initial Access', 'Execution', 'Persistence', 'Privilege Escalation'],
            y=['T1', 'T2'],
            colorscale=[[0, '#FEE2E2'], [0.4, '#FEF3C7'], [0.7, '#D1FAE5'], [1, '#10B981']]
        ))
        fig.update_layout(
            title="MITRE ATT&CK Coverage Heatmap",
            xaxis_nticks=14
        )
        return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    def _get_rag_color(self, rag_status: str) -> str:
        # Color mapping extracted from RAG_STATUS_MAP logic
        if rag_status == "Green": return "#10b981"
        if rag_status == "Amber": return "#f59e0b"
        if rag_status == "Red": return "#ef4444"
        return "#9ca3af"
