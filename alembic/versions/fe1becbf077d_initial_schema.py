"""Initial schema

Revision ID: fe1becbf077d
Revises:
Create Date: 2026-06-23 22:53:50.966326
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "fe1becbf077d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "metric_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("metric_id", sa.String(length=100), nullable=False),
        sa.Column("metric_name", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("rag_status", sa.String(length=20), nullable=False),
        sa.Column("ale_usd", sa.Float(), nullable=True),
        sa.Column("var_95_usd", sa.Float(), nullable=True),
        sa.Column("probability_of_breach", sa.Float(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_history_metric_id", "metric_history", ["metric_id"])
    op.create_index("ix_metric_history_run_id", "metric_history", ["run_id"])
    op.create_index("ix_metric_history_tenant_id", "metric_history", ["tenant_id"])
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.String(length=100), nullable=False),
        sa.Column("pdf_path", sa.String(length=500), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("threshold_hash", sa.String(length=64), nullable=False),
        sa.Column("metric_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_run_id", "reports", ["run_id"], unique=True)
    op.create_index("ix_reports_tenant_id", "reports", ["tenant_id"])
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("metric_id", sa.String(length=100), nullable=False),
        sa.Column("metric_name", sa.String(length=200), nullable=False),
        sa.Column("rag_status", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("channels_notified", sa.JSON(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=100), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_metric_id", "alerts", ["metric_id"])
    op.create_index("ix_alerts_run_id", "alerts", ["run_id"])
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_table(
        "integration_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("slack_webhook_url", sa.String(length=500), nullable=True),
        sa.Column("teams_webhook_url", sa.String(length=500), nullable=True),
        sa.Column("pagerduty_routing_key", sa.String(length=100), nullable=True),
        sa.Column("siem_type", sa.String(length=50), nullable=False),
        sa.Column("siem_url", sa.String(length=500), nullable=True),
        sa.Column("siem_api_key", sa.String(length=500), nullable=True),
        sa.Column("onboarded", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integration_settings_tenant_id", "integration_settings", ["tenant_id"], unique=True)
    op.create_table(
        "audit_findings",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metric_id", sa.String(length=100), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("owner_username", sa.String(length=100), nullable=True),
        sa.Column("remediation_plan", sa.Text(), nullable=True),
        sa.Column("evidence_file_name", sa.String(length=200), nullable=True),
        sa.Column("evidence_hash", sa.String(length=64), nullable=True),
        sa.Column("evidence_id", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_findings_tenant_id", "audit_findings", ["tenant_id"])
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("run_id", sa.String(length=100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_records_evidence_id", "evidence_records", ["evidence_id"], unique=True)
    op.create_index("ix_evidence_records_tenant_id", "evidence_records", ["tenant_id"])
    op.create_table(
        "timeline_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timeline_snapshots_snapshot_at", "timeline_snapshots", ["snapshot_at"])
    op.create_index("ix_timeline_snapshots_tenant_id", "timeline_snapshots", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("timeline_snapshots")
    op.drop_table("evidence_records")
    op.drop_table("audit_findings")
    op.drop_table("integration_settings")
    op.drop_table("alerts")
    op.drop_table("reports")
    op.drop_table("metric_history")
    op.drop_table("users")
    op.drop_table("tenants")
