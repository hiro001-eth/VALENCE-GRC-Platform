"""Database session factory for VALENCE GRC Dashboard."""
import os
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from grc_dashboard.auth.demo_credentials import (
    ensure_demo_credential_file,
    resolve_demo_password,
    seed_demo_users_enabled,
)
from grc_dashboard.auth.jwt_handler import hash_password
from grc_dashboard.db.migrations import sync_model_schema
from grc_dashboard.db.models import Base

logger = structlog.get_logger(__name__)

from grc_dashboard.config import resolve_database_url

DATABASE_URL = resolve_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=(
        {"check_same_thread": False, "timeout": 30}
        if "sqlite" in DATABASE_URL
        else {}
    ),
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    import asyncio

    from grc_dashboard.db.alembic_runner import run_alembic_upgrade

    use_alembic = (
        "postgresql" in DATABASE_URL
        or os.getenv("VALENCE_USE_ALEMBIC", "false").lower() in {"1", "true", "yes"}
    )

    if use_alembic:
        await asyncio.to_thread(run_alembic_upgrade)
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await sync_model_schema(engine, DATABASE_URL)

    if "sqlite" in DATABASE_URL:
        await _ensure_user_columns()
        await _ensure_tenant_columns()
        await _ensure_integration_columns()
        await _ensure_vendor_columns()
        await _ensure_training_columns()
        await _ensure_trust_questionnaire_columns()

    await _seed_platform()
    await _seed_demo_vendors()
    logger.info("database_initialized", url=DATABASE_URL.split("@")[-1], alembic=use_alembic)


async def _ensure_user_columns() -> None:
    """Add feature columns to existing SQLite databases without Alembic."""
    if "sqlite" not in DATABASE_URL:
        return
    import sqlalchemy as sa

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            rows = sync_conn.execute(sa.text("PRAGMA table_info(users)")).fetchall()
            cols = {row[1] for row in rows}
            if "department" not in cols:
                sync_conn.execute(
                    sa.text("ALTER TABLE users ADD COLUMN department VARCHAR(50) DEFAULT 'general'")
                )
            if "feature_permissions" not in cols:
                sync_conn.execute(sa.text("ALTER TABLE users ADD COLUMN feature_permissions JSON"))

        await conn.run_sync(migrate)


async def _ensure_tenant_columns() -> None:
    if "sqlite" not in DATABASE_URL:
        return
    import sqlalchemy as sa

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            rows = sync_conn.execute(sa.text("PRAGMA table_info(tenants)")).fetchall()
            cols = {row[1] for row in rows}
            additions = [
                ("plan", "VARCHAR(50) DEFAULT 'trial'"),
                ("stripe_customer_id", "VARCHAR(100)"),
                ("stripe_subscription_id", "VARCHAR(100)"),
                ("subscription_status", "VARCHAR(50) DEFAULT 'trialing'"),
                ("trial_ends_at", "DATETIME"),
            ]
            for name, typedef in additions:
                if name not in cols:
                    sync_conn.execute(sa.text(f"ALTER TABLE tenants ADD COLUMN {name} {typedef}"))

        await conn.run_sync(migrate)


async def _ensure_integration_columns() -> None:
    if "sqlite" not in DATABASE_URL:
        return
    import sqlalchemy as sa

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            rows = sync_conn.execute(sa.text("PRAGMA table_info(integration_settings)")).fetchall()
            cols = {row[1] for row in rows}
            if "connected_integrations" not in cols:
                sync_conn.execute(
                    sa.text("ALTER TABLE integration_settings ADD COLUMN connected_integrations JSON")
                )

        await conn.run_sync(migrate)


async def _ensure_vendor_columns() -> None:
    import sqlalchemy as sa

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            if "sqlite" in DATABASE_URL:
                rows = sync_conn.execute(sa.text("PRAGMA table_info(vendor_records)")).fetchall()
                if not rows:
                    return
                cols = {row[1] for row in rows}
            else:
                result = sync_conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'vendor_records'"
                    )
                )
                cols = {row[0] for row in result.fetchall()}
                if not cols:
                    return

            additions = [
                ("questionnaire_responses", "JSON"),
            ]
            for name, typedef in additions:
                if name not in cols:
                    sync_conn.execute(sa.text(f"ALTER TABLE vendor_records ADD COLUMN {name} {typedef}"))

        await conn.run_sync(migrate)


async def _ensure_training_columns() -> None:
    import sqlalchemy as sa

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            if "sqlite" in DATABASE_URL:
                rows = sync_conn.execute(sa.text("PRAGMA table_info(training_courses)")).fetchall()
                if not rows:
                    return
                cols = {row[1] for row in rows}
            else:
                result = sync_conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'training_courses'"
                    )
                )
                cols = {row[0] for row in result.fetchall()}
                if not cols:
                    return

            additions = [
                ("content_type", "VARCHAR(20) DEFAULT 'article'"),
                ("content_url", "VARCHAR(500)"),
                ("scorm_package", "VARCHAR(500)"),
                ("video_url", "VARCHAR(500)"),
                ("quiz_questions", "JSON"),
            ]
            for name, typedef in additions:
                if name not in cols:
                    sync_conn.execute(sa.text(f"ALTER TABLE training_courses ADD COLUMN {name} {typedef}"))

            if "sqlite" in DATABASE_URL:
                rows2 = sync_conn.execute(sa.text("PRAGMA table_info(training_completions)")).fetchall()
                cols2 = {row[1] for row in rows2}
            else:
                result2 = sync_conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'training_completions'"
                    )
                )
                cols2 = {row[0] for row in result2.fetchall()}

            if cols2 and "progress_pct" not in cols2:
                sync_conn.execute(
                    sa.text("ALTER TABLE training_completions ADD COLUMN progress_pct FLOAT DEFAULT 100.0")
                )

        await conn.run_sync(migrate)


async def _ensure_trust_questionnaire_columns() -> None:
    import sqlalchemy as sa

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            for table, additions in (
                (
                    "trust_center_config",
                    [
                        ("nda_required", "BOOLEAN DEFAULT 0"),
                        ("nda_text", "TEXT"),
                    ],
                ),
                (
                    "security_questionnaire_profiles",
                    [
                        ("approval_status", "VARCHAR(30) DEFAULT 'draft'"),
                        ("approved_by", "VARCHAR(100)"),
                    ],
                ),
            ):
                if "sqlite" in DATABASE_URL:
                    rows = sync_conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
                    if not rows:
                        continue
                    cols = {row[1] for row in rows}
                else:
                    result = sync_conn.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns "
                            f"WHERE table_name = '{table}'"
                        )
                    )
                    cols = {row[0] for row in result.fetchall()}
                    if not cols:
                        continue
                for name, typedef in additions:
                    if name not in cols:
                        sync_conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {name} {typedef}"))

        await conn.run_sync(migrate)


async def _seed_demo_vendors() -> None:
    from grc_dashboard.api.routers.vendors import _ensure_demo_vendors
    from grc_dashboard.tenancy.constants import DEMO_TENANT_IDS

    async with AsyncSessionLocal() as session:
        for tenant_id in DEMO_TENANT_IDS:
            await _ensure_demo_vendors(session, tenant_id)


async def _seed_platform() -> None:
    from sqlalchemy import select

    from grc_dashboard.db.models import User
    from grc_dashboard.tenancy.constants import DEMO_TENANT_IDS
    from grc_dashboard.tenancy.service import ensure_demo_tenants

    if not seed_demo_users_enabled():
        logger.info("demo_user_seeding_disabled")
        return

    ensure_demo_credential_file()

    async with AsyncSessionLocal() as session:
        await ensure_demo_tenants(session)

        result = await session.execute(select(User).where(User.username == "admin"))
        if result.scalar_one_or_none():
            return

        roles = [
            ("admin", "VALENCE Administrator", "admin"),
            ("ciso", "Chief Information Security Officer", "ciso"),
            ("analyst", "Security Analyst", "analyst"),
            ("auditor", "Compliance Auditor", "auditor"),
        ]
        users = [
            User(
                tenant_id="demo-global-hq",
                username=username,
                email=f"{username}@valence-grc.internal",
                hashed_password=hash_password(resolve_demo_password(username)),
                full_name=full_name,
                role=role,
            )
            for username, full_name, role in roles
        ]
        session.add_all(users)
        await session.commit()
        logger.info(
            "demo_accounts_seeded",
            count=len(users),
            demo_tenants=list(DEMO_TENANT_IDS),
        )
