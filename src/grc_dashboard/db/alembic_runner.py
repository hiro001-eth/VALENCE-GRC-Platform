"""Run Alembic migrations programmatically (Postgres production path)."""
from __future__ import annotations

import os
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config

logger = structlog.get_logger(__name__)


def _sync_database_url(async_url: str) -> str:
    """Convert async SQLAlchemy URL to sync driver for Alembic."""
    url = async_url.strip()
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return url


def run_alembic_upgrade(revision: str = "head") -> None:
    """Apply pending Alembic revisions."""
    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./valence.db")
    cfg.set_main_option("sqlalchemy.url", _sync_database_url(db_url))
    command.upgrade(cfg, revision)
    logger.info("alembic_upgrade_complete", revision=revision)
