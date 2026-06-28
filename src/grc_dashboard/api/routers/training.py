"""Employee security awareness training tracking."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin, RequireAnalyst, RequireAuditor
from grc_dashboard.db.models import TrainingCompletion, TrainingCourse, User
from grc_dashboard.db.persistence import append_evidence_record
from grc_dashboard.db.session import get_db
from grc_dashboard.tenancy.constants import is_demo_tenant

router = APIRouter()

DEFAULT_COURSES = [
    ("TRN-SEC-001", "Security Awareness Fundamentals", "security", 45, True,
     "Phishing recognition, password hygiene, and incident reporting.", "article",
     None, None, None),
    ("TRN-PHI-001", "HIPAA / PHI Handling", "privacy", 30, True,
     "Protected health information handling.", "scorm", None, "/static/scorm/hipaa-starter.zip", None),
    ("TRN-IR-001", "Incident Response Basics", "operations", 25, True,
     "Escalation and evidence preservation.", "quiz", None, None,
     [{"q": "Who do you notify for a Sev-1 incident?", "a": "CISO and IR team"}]),
    ("TRN-GDPR-001", "GDPR & Data Privacy", "privacy", 20, False,
     "Lawful basis and breach notification.", "article", None, None, None),
]


class CompleteTraining(BaseModel):
    course_id: str
    score: float = 100.0
    progress_pct: float = 100.0


class ProgressUpdate(BaseModel):
    course_id: str
    progress_pct: float


async def _sync_demo_courses(session: AsyncSession, tenant_id: str) -> None:
    """Create or refresh demo courses (fixes legacy rows missing video/scorm/quiz types)."""
    if not is_demo_tenant(tenant_id):
        return
    changed = False
    for cid, title, cat, dur, req, desc, ctype, video, scorm, quiz in DEFAULT_COURSES:
        result = await session.execute(
            select(TrainingCourse).where(
                TrainingCourse.id == cid,
                TrainingCourse.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.title = title
            row.category = cat
            row.duration_minutes = dur
            row.required = req
            row.description = desc
            row.content_type = ctype
            row.video_url = video
            row.scorm_package = scorm
            row.quiz_questions = quiz
            changed = True
        else:
            session.add(
                TrainingCourse(
                    id=cid,
                    tenant_id=tenant_id,
                    title=title,
                    category=cat,
                    duration_minutes=dur,
                    required=req,
                    description=desc,
                    content_type=ctype,
                    video_url=video,
                    scorm_package=scorm,
                    quiz_questions=quiz,
                )
            )
            changed = True
    if changed:
        await session.commit()


async def _ensure_demo_courses(session: AsyncSession, tenant_id: str) -> None:
    await _sync_demo_courses(session, tenant_id)


@router.get("/courses")
async def list_courses(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_courses(db, tenant_id)
    result = await db.execute(
        select(TrainingCourse).where(TrainingCourse.tenant_id == tenant_id).order_by(TrainingCourse.title)
    )
    completions = await db.execute(
        select(TrainingCompletion.course_id).where(
            TrainingCompletion.tenant_id == tenant_id,
            TrainingCompletion.username == current_user.username,
        )
    )
    done = {row[0] for row in completions.all()}
    return [
        {
            "id": c.id,
            "title": c.title,
            "category": c.category,
            "duration_minutes": c.duration_minutes,
            "required": c.required,
            "description": c.description,
            "content_type": c.content_type,
            "video_url": c.video_url,
            "scorm_package": c.scorm_package,
            "quiz_questions": c.quiz_questions or [],
            "completed": c.id in done,
        }
        for c in result.scalars().all()
    ]


@router.get("/summary")
async def training_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAuditor,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    await _ensure_demo_courses(db, tenant_id)
    required = await db.execute(
        select(func.count()).select_from(TrainingCourse).where(
            TrainingCourse.tenant_id == tenant_id,
            TrainingCourse.required.is_(True),
        )
    )
    completions = await db.execute(
        select(func.count()).select_from(TrainingCompletion).where(TrainingCompletion.tenant_id == tenant_id)
    )
    users_done = await db.execute(
        select(func.count(func.distinct(TrainingCompletion.username))).where(
            TrainingCompletion.tenant_id == tenant_id
        )
    )
    req_count = required.scalar() or 0
    comp_count = completions.scalar() or 0
    user_required_done = await db.execute(
        select(func.count()).select_from(TrainingCompletion).where(
            TrainingCompletion.tenant_id == tenant_id,
            TrainingCompletion.username == current_user.username,
            TrainingCompletion.course_id.in_(
                select(TrainingCourse.id).where(
                    TrainingCourse.tenant_id == tenant_id,
                    TrainingCourse.required.is_(True),
                )
            ),
        )
    )
    user_done = user_required_done.scalar() or 0
    return {
        "required_courses": req_count,
        "total_completions": comp_count,
        "users_with_completions": users_done.scalar() or 0,
        "your_completion_pct": round((user_done / max(req_count, 1)) * 100, 1),
        "org_completion_pct": round(min((comp_count / max(req_count * 4, 1)) * 100, 100), 1),
    }


@router.post("/complete")
async def complete_training(
    body: CompleteTraining,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    result = await db.execute(
        select(TrainingCourse).where(
            TrainingCourse.id == body.course_id,
            TrainingCourse.tenant_id == tenant_id,
        )
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = await db.execute(
        select(TrainingCompletion).where(
            TrainingCompletion.tenant_id == tenant_id,
            TrainingCompletion.course_id == body.course_id,
            TrainingCompletion.username == current_user.username,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already completed")

    now = datetime.now(UTC)
    evidence = await append_evidence_record(
        db,
        tenant_id,
        event_type="training_completion",
        category="audit_evidence",
        data={
            "course_id": body.course_id,
            "course_title": course.title,
            "username": current_user.username,
            "score": body.score,
        },
        run_id="TRAINING",
    )
    row = TrainingCompletion(
        tenant_id=tenant_id,
        course_id=body.course_id,
        username=current_user.username,
        score=body.score,
        progress_pct=body.progress_pct,
        completed_at=now,
        evidence_id=evidence.get("evidence_id"),
    )
    db.add(row)
    await db.commit()
    return {"status": "completed", "course_id": body.course_id, "evidence_id": evidence.get("evidence_id")}


@router.post("/seed")
async def seed_training_courses(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    created = 0
    for cid, title, cat, dur, req, desc, ctype, video, scorm, quiz in DEFAULT_COURSES:
        exists = await db.execute(
            select(TrainingCourse).where(TrainingCourse.id == cid, TrainingCourse.tenant_id == tenant_id)
        )
        if exists.scalar_one_or_none():
            continue
        db.add(
            TrainingCourse(
                id=f"{cid}-{uuid.uuid4().hex[:4].upper()}",
                tenant_id=tenant_id,
                title=title,
                category=cat,
                duration_minutes=dur,
                required=req,
                description=desc,
                content_type=ctype,
                video_url=video,
                scorm_package=scorm,
                quiz_questions=quiz,
            )
        )
        created += 1
    await db.commit()
    return {"status": "success", "courses_created": created}


@router.post("/progress")
async def update_training_progress(
    body: ProgressUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAnalyst,
) -> dict[str, Any]:
    """Track SCORM/video progress before final completion."""
    return {
        "course_id": body.course_id,
        "progress_pct": body.progress_pct,
        "username": current_user.username,
        "status": "in_progress",
    }
