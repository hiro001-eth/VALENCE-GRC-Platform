"""Policy library and employee attestation workflows."""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst, RequireAuditor
from grc_dashboard.db.models import PolicyAttestation, PolicyRecord, User
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

logger = structlog.get_logger(__name__)
router = APIRouter()

POLICY_TEMPLATES = [
    {
        "title": "Information Security Policy",
        "category": "security",
        "framework_tags": ["SOC2", "ISO27001", "HIPAA"],
        "content": (
            "This policy establishes requirements for protecting information assets, "
            "including access control, encryption, incident response, and acceptable use. "
            "All personnel must complete annual security awareness training."
        ),
    },
    {
        "title": "Acceptable Use Policy",
        "category": "hr",
        "framework_tags": ["SOC2", "GDPR"],
        "content": (
            "Employees shall use company systems only for authorized business purposes. "
            "Prohibited activities include unauthorized data exfiltration, sharing credentials, "
            "and installing unapproved software."
        ),
    },
    {
        "title": "Data Classification & Handling",
        "category": "privacy",
        "framework_tags": ["GDPR", "HIPAA", "PCI_DSS"],
        "content": (
            "Data is classified as Public, Internal, Confidential, or Restricted. "
            "PHI and cardholder data require encryption at rest and in transit. "
            "Cross-border transfers require documented legal basis."
        ),
    },
    {
        "title": "Vendor Risk Management Policy",
        "category": "vendor",
        "framework_tags": ["SOC2", "NIST_CSF"],
        "content": (
            "Third-party vendors handling sensitive data must complete security questionnaires "
            "and maintain contractual SLAs. Critical vendors require annual reassessment."
        ),
    },
    {
        "title": "Incident Response Plan",
        "category": "operations",
        "framework_tags": ["SOC2", "NIS2", "DORA"],
        "content": (
            "Security incidents are classified by severity. MTTD and MTTR targets apply. "
            "Material incidents require executive notification within 4 hours and regulator "
            "notification per jurisdictional requirements."
        ),
    },
]


class PolicyCreate(BaseModel):
    title: str
    category: str = "security"
    version: str = "1.0"
    content: str = ""
    owner: str | None = None
    framework_tags: list[str] = Field(default_factory=list)
    requires_attestation: bool = True
    status: str = "published"


class PolicyUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    version: str | None = None
    content: str | None = None
    status: str | None = None
    framework_tags: list[str] | None = None
    requires_attestation: bool | None = None


class AttestBody(BaseModel):
    policy_id: str


async def _ensure_demo_policies(session: AsyncSession, tenant_id: str) -> None:
    if not is_demo_tenant(tenant_id):
        return
    existing = await session.execute(
        select(PolicyRecord.id).where(PolicyRecord.tenant_id == tenant_id).limit(1)
    )
    if existing.scalar_one_or_none():
        return
    for i, tpl in enumerate(POLICY_TEMPLATES):
        session.add(
            PolicyRecord(
                id=f"POL-{tenant_id[:8].upper()}-{i+1:03d}",
                tenant_id=tenant_id,
                title=tpl["title"],
                category=tpl["category"],
                version="1.0",
                content=tpl["content"],
                status="published",
                owner="ciso",
                framework_tags=tpl["framework_tags"],
                requires_attestation=True,
            )
        )
    await session.commit()


def _policy_row(p: PolicyRecord, attested: bool = False) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "category": p.category,
        "version": p.version,
        "content": p.content,
        "status": p.status,
        "owner": p.owner,
        "framework_tags": p.framework_tags or [],
        "requires_attestation": p.requires_attestation,
        "user_attested": attested,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/templates")
async def list_policy_templates(current_user: User = RequireAuditor) -> list[dict[str, Any]]:
    return POLICY_TEMPLATES


@router.get("/")
async def list_policies(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_policies(db, tenant_id)
    result = await db.execute(
        select(PolicyRecord).where(PolicyRecord.tenant_id == tenant_id).order_by(PolicyRecord.title)
    )
    policies = result.scalars().all()
    att_result = await db.execute(
        select(PolicyAttestation.policy_id).where(
            PolicyAttestation.tenant_id == tenant_id,
            PolicyAttestation.username == current_user.username,
        )
    )
    attested_ids = {row[0] for row in att_result.all()}
    return [_policy_row(p, p.id in attested_ids) for p in policies]


@router.post("/", status_code=201)
async def create_policy(
    body: PolicyCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    policy_id = f"POL-{uuid.uuid4().hex[:8].upper()}"
    row = PolicyRecord(
        id=policy_id,
        tenant_id=tenant_id,
        title=body.title.strip(),
        category=body.category,
        version=body.version,
        content=body.content,
        status=body.status,
        owner=body.owner or current_user.username,
        framework_tags=body.framework_tags,
        requires_attestation=body.requires_attestation,
    )
    db.add(row)
    await db.commit()
    return _policy_row(row)


@router.put("/{policy_id}")
async def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(PolicyRecord).where(
            PolicyRecord.id == policy_id,
            PolicyRecord.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")

    if body.title is not None:
        row.title = body.title.strip()
    if body.category is not None:
        row.category = body.category
    if body.version is not None:
        row.version = body.version
    if body.content is not None:
        row.content = body.content
    if body.status is not None:
        row.status = body.status
    if body.framework_tags is not None:
        row.framework_tags = body.framework_tags
    if body.requires_attestation is not None:
        row.requires_attestation = body.requires_attestation

    row.updated_at = datetime.now(UTC)
    await db.commit()
    return _policy_row(row)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> None:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(PolicyRecord).where(
            PolicyRecord.id == policy_id,
            PolicyRecord.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(row)
    await db.commit()


@router.post("/seed-templates")
async def seed_policy_templates(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    created = 0
    for i, tpl in enumerate(POLICY_TEMPLATES):
        pid = f"POL-{uuid.uuid4().hex[:6].upper()}"
        db.add(
            PolicyRecord(
                id=pid,
                tenant_id=tenant_id,
                title=tpl["title"],
                category=tpl["category"],
                version="1.0",
                content=tpl["content"],
                status="published",
                owner=current_user.username,
                framework_tags=tpl["framework_tags"],
                requires_attestation=True,
            )
        )
        created += 1
    await db.commit()
    return {"status": "success", "policies_created": created}


@router.get("/attestations/summary")
async def attestation_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_policies(db, tenant_id)
    policies = await db.execute(
        select(PolicyRecord).where(
            PolicyRecord.tenant_id == tenant_id,
            PolicyRecord.requires_attestation.is_(True),
            PolicyRecord.status == "published",
        )
    )
    required = list(policies.scalars().all())
    attestations = await db.execute(
        select(PolicyAttestation).where(PolicyAttestation.tenant_id == tenant_id)
    )
    rows = attestations.scalars().all()
    by_user: dict[str, int] = {}
    for a in rows:
        by_user[a.username] = by_user.get(a.username, 0) + 1
    total_required = len(required)
    total_attestations = len(rows)
    completion_pct = round(
        (total_attestations / (total_required * max(len(by_user), 1))) * 100, 1
    ) if total_required else 100.0
    return {
        "policies_requiring_attestation": total_required,
        "total_attestations": total_attestations,
        "unique_users_attested": len(by_user),
        "completion_pct": min(completion_pct, 100.0),
        "by_user": by_user,
    }


@router.post("/attest")
async def attest_policy(
    body: AttestBody,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(PolicyRecord).where(
            PolicyRecord.id == body.policy_id,
            PolicyRecord.tenant_id == tenant_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    existing = await db.execute(
        select(PolicyAttestation).where(
            PolicyAttestation.tenant_id == tenant_id,
            PolicyAttestation.policy_id == body.policy_id,
            PolicyAttestation.username == current_user.username,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already attested to this policy")

    now = datetime.now(UTC)
    payload = f"{tenant_id}:{body.policy_id}:{current_user.username}:{now.isoformat()}"
    sig_hash = hashlib.sha256(payload.encode()).hexdigest()

    evidence = await append_evidence_record(
        db,
        tenant_id,
        event_type="policy_attestation",
        category="audit_evidence",
        data={
            "policy_id": body.policy_id,
            "policy_title": policy.title,
            "username": current_user.username,
            "signature_hash": sig_hash,
        },
        run_id="POLICY_ATTEST",
    )

    att = PolicyAttestation(
        tenant_id=tenant_id,
        policy_id=body.policy_id,
        username=current_user.username,
        attested_at=now,
        signature_hash=sig_hash,
        evidence_id=evidence.get("evidence_id"),
    )
    db.add(att)
    await db.commit()
    return {
        "status": "attested",
        "policy_id": body.policy_id,
        "signature_hash": sig_hash,
        "evidence_id": evidence.get("evidence_id"),
    }
