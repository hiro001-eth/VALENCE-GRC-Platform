"""Apply additive schema migrations so existing DBs match SQLAlchemy models."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _column_default_clause(col: Any) -> str:
    if col.server_default is not None:
        try:
            arg = col.server_default.arg
            if isinstance(arg, str):
                return f" DEFAULT '{arg}'"
            if arg is not None:
                return f" DEFAULT {arg}"
        except Exception:
            pass
    default = col.default
    if default is not None and getattr(default, "is_scalar", False):
        val = default.arg
        if isinstance(val, bool):
            return f" DEFAULT {1 if val else 0}"
        if isinstance(val, (int, float)):
            return f" DEFAULT {val}"
        if isinstance(val, str):
            return f" DEFAULT '{val}'"
    return ""


async def sync_model_schema(engine: Any, database_url: str) -> None:
    """Add any ORM columns missing from existing tables (SQLite + Postgres)."""
    import sqlalchemy as sa

    from grc_dashboard.db.models import Base

    is_sqlite = "sqlite" in database_url

    async with engine.begin() as conn:
        def migrate(sync_conn: Any) -> None:
            dialect = sync_conn.dialect
            for table_name, table in Base.metadata.tables.items():
                if is_sqlite:
                    rows = sync_conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
                    if not rows:
                        continue
                    existing = {row[1] for row in rows}
                else:
                    result = sync_conn.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :tname"
                        ),
                        {"tname": table_name},
                    )
                    existing = {row[0] for row in result.fetchall()}
                    if not existing:
                        continue

                for col in table.columns:
                    if col.name in existing:
                        continue
                    type_sql = col.type.compile(dialect=dialect)
                    default_sql = _column_default_clause(col)
                    stmt = (
                        f"ALTER TABLE {table_name} ADD COLUMN {col.name} "
                        f"{type_sql}{default_sql}"
                    )
                    try:
                        sync_conn.execute(sa.text(stmt))
                        logger.info("schema_column_added", table=table_name, column=col.name)
                    except Exception as exc:
                        logger.warning(
                            "schema_column_add_failed",
                            table=table_name,
                            column=col.name,
                            error=str(exc),
                        )

        await conn.run_sync(migrate)
