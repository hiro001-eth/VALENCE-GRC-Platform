"""Full schema from ORM models — Alembic-first production migrations.

Revision ID: b7e4a1c92f30
Revises: fe1becbf077d
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4a1c92f30"
down_revision: Union[str, Sequence[str], None] = "fe1becbf077d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    from grc_dashboard.db.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind, checkfirst=True)
    inspector = sa.inspect(bind)

    tenant_cols = _column_names(inspector, "tenants")
    if tenant_cols:
        additions = [
            ("plan", sa.String(50), "trial"),
            ("stripe_customer_id", sa.String(100), None),
            ("stripe_subscription_id", sa.String(100), None),
            ("subscription_status", sa.String(50), "trialing"),
            ("trial_ends_at", sa.DateTime(timezone=True), None),
        ]
        for name, col_type, default in additions:
            if name not in tenant_cols:
                op.add_column("tenants", sa.Column(name, col_type, nullable=True))
                if default is not None:
                    op.execute(sa.text(f"UPDATE tenants SET {name} = '{default}' WHERE {name} IS NULL"))

    user_cols = _column_names(inspector, "users")
    if user_cols:
        if "department" not in user_cols:
            op.add_column("users", sa.Column("department", sa.String(50), server_default="general"))
        if "feature_permissions" not in user_cols:
            op.add_column("users", sa.Column("feature_permissions", sa.JSON(), nullable=True))

    int_cols = _column_names(inspector, "integration_settings")
    if int_cols and "connected_integrations" not in int_cols:
        op.add_column("integration_settings", sa.Column("connected_integrations", sa.JSON(), nullable=True))


def downgrade() -> None:
    pass
