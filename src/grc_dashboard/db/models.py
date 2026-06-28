"""Database models for VALENCE GRC Dashboard."""
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(100), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str] = mapped_column(String(50), default="trial")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(50), default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(50), default="analyst")
    # Roles: admin | ciso | analyst | auditor
    department: Mapped[str] = mapped_column(String(50), default="general")
    feature_permissions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MetricHistoryRecord(Base):
    __tablename__ = "metric_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", index=True)
    run_id: Mapped[str] = mapped_column(String(100), index=True)
    metric_id: Mapped[str] = mapped_column(String(100), index=True)
    metric_name: Mapped[str] = mapped_column(String(200), default="")
    value: Mapped[float] = mapped_column(Float)
    rag_status: Mapped[str] = mapped_column(String(20))
    ale_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    var_95_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_of_breach: Mapped[float | None] = mapped_column(Float, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReportRecord(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", index=True)
    run_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_by: Mapped[str] = mapped_column(String(100), default="system")
    pdf_path: Mapped[str] = mapped_column(String(500))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    threshold_hash: Mapped[str] = mapped_column(String(64))
    metric_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AlertRecord(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", index=True)
    run_id: Mapped[str] = mapped_column(String(100), index=True)
    metric_id: Mapped[str] = mapped_column(String(100), index=True)
    metric_name: Mapped[str] = mapped_column(String(200), default="")
    rag_status: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20), default="high")
    message: Mapped[str] = mapped_column(Text)
    channels_notified: Mapped[list[Any]] = mapped_column(JSON, default=list)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IntegrationSettings(Base):
    __tablename__ = "integration_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", unique=True, index=True)
    slack_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    teams_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pagerduty_routing_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # SIEM Configuration
    siem_type: Mapped[str] = mapped_column(String(50), default="Demo") # Splunk | Elastic | CSV
    siem_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    siem_api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    connected_integrations: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    framework: Mapped[str] = mapped_column(String(50), default="SOC2")
    control_id: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(100))
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    evidence_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VendorRecord(Base):
    __tablename__ = "vendor_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(50), default="operational")
    questionnaire_score: Mapped[float] = mapped_column(Float, default=70.0)
    data_classification: Mapped[str] = mapped_column(String(50), default="internal")
    incident_count: Mapped[int] = mapped_column(default=0)
    contract_sla_score: Mapped[float] = mapped_column(Float, default=80.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_tier: Mapped[str] = mapped_column(String(20), default="medium")
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    questionnaire_responses: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RiskRegisterEntry(Base):
    __tablename__ = "risk_register"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    cve_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(20), default="high")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open")
    source: Mapped[str] = mapped_column(String(50), default="cerberus")
    metric_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finding_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[str] = mapped_column(String(50), primary_key=True) # FIND-001, etc.
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="high") # critical | high | medium | low
    status: Mapped[str] = mapped_column(String(50), default="finding") # finding | assigned | remediation_plan | evidence_upload | closed
    owner_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remediation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[str] = mapped_column(String(100), default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    previous_hash: Mapped[str] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    frequency: Mapped[str] = mapped_column(String(20), default="weekly")
    framework: Mapped[str] = mapped_column(String(50), default="SOC2")
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TimelineSnapshot(Base):
    __tablename__ = "timeline_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metrics: Mapped[list[Any]] = mapped_column(JSON, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PolicyRecord(Base):
    __tablename__ = "policy_records"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), default="security")
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    framework_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    requires_attestation: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolicyAttestation(Base):
    __tablename__ = "policy_attestations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    policy_id: Mapped[str] = mapped_column(String(50), index=True)
    username: Mapped[str] = mapped_column(String(100))
    attested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signature_hash: Mapped[str] = mapped_column(String(64))
    evidence_id: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PersonnelEvent(Base):
    """Joiner / mover / leaver lifecycle events for access review evidence."""

    __tablename__ = "personnel_events"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    employee_email: Mapped[str] = mapped_column(String(255))
    employee_name: Mapped[str] = mapped_column(String(200), default="")
    department: Mapped[str] = mapped_column(String(100), default="")
    source: Mapped[str] = mapped_column(String(50), default="manual")
    access_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeviceComplianceRecord(Base):
    __tablename__ = "device_compliance"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    device_name: Mapped[str] = mapped_column(String(200), default="")
    owner_email: Mapped[str] = mapped_column(String(255), default="")
    platform: Mapped[str] = mapped_column(String(50), default="unknown")
    mdm_enrolled: Mapped[bool] = mapped_column(Boolean, default=False)
    disk_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    os_version: Mapped[str] = mapped_column(String(50), default="")
    compliance_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrustCenterConfig(Base):
    __tablename__ = "trust_center_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    public_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    frameworks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    badges: Mapped[list[Any]] = mapped_column(JSON, default=list)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nda_required: Mapped[bool] = mapped_column(Boolean, default=False)
    nda_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SecurityQuestionnaireProfile(Base):
    __tablename__ = "security_questionnaire_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    company_legal_name: Mapped[str] = mapped_column(String(200), default="")
    responses: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    auto_fill_version: Mapped[str] = mapped_column(String(20), default="1.0")
    approval_status: Mapped[str] = mapped_column(String(30), default="draft")
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingCourse(Base):
    __tablename__ = "training_courses"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), default="security")
    duration_minutes: Mapped[int] = mapped_column(default=30)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(20), default="article")
    content_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scorm_package: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quiz_questions: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingCompletion(Base):
    __tablename__ = "training_completions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    course_id: Mapped[str] = mapped_column(String(50), index=True)
    username: Mapped[str] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(Float, default=100.0)
    progress_pct: Mapped[float] = mapped_column(Float, default=100.0)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_id: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PenTestEngagement(Base):
    __tablename__ = "pentest_engagements"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    vendor: Mapped[str] = mapped_column(String(200), default="")
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="scheduled")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    findings_critical: Mapped[int] = mapped_column(default=0)
    findings_high: Mapped[int] = mapped_column(default=0)
    findings_medium: Mapped[int] = mapped_column(default=0)
    report_evidence_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VendorBreachAlert(Base):
    __tablename__ = "vendor_breach_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    vendor_name: Mapped[str] = mapped_column(String(200), index=True)
    breach_source: Mapped[str] = mapped_column(String(100), default="monitor")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    breach_date: Mapped[str] = mapped_column(String(20), default="")
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RemediationTask(Base):
    __tablename__ = "remediation_tasks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)
    control_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finding_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sla_hours: Mapped[int] = mapped_column(default=72)
    external_ticket_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_ticket_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BusinessUnit(Base):
    __tablename__ = "business_units"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50), default="")
    parent_bu_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str] = mapped_column(String(100), default="")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    bu_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(String(50), default="manual")
    steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CmdbAsset(Base):
    __tablename__ = "cmdb_assets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    bu_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_type: Mapped[str] = mapped_column(String(50), default="application")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    criticality: Mapped[str] = mapped_column(String(20), default="medium")
    source_integration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    asset_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ItsTicketRecord(Base):
    __tablename__ = "itsm_tickets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    remediation_task_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(30))
    external_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    summary: Mapped[str] = mapped_column(String(300), default="")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    bu_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(String(50), default="application")
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    requested_by: Mapped[str] = mapped_column(String(100), default="system")
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    implemented_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    implementation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_ticket_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_ticket_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), default="stripe")
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), default="")
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditorFirm(Base):
    __tablename__ = "auditor_firms"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    specializations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    regions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    soc2_accredited: Mapped[bool] = mapped_column(Boolean, default=True)
    iso27001_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    rating: Mapped[float] = mapped_column(Float, default=4.5)
    hourly_rate_usd: Mapped[int] = mapped_column(default=250)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditorEngagement(Base):
    __tablename__ = "auditor_engagements"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    firm_id: Mapped[str] = mapped_column(String(50), index=True)
    framework: Mapped[str] = mapped_column(String(50), default="SOC2")
    status: Mapped[str] = mapped_column(String(30), default="requested")
    auditor_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scope_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
