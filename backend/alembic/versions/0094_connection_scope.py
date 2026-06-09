"""connection scope — multi-app / tenant-wide reach for comm connections.

Adds ``tenant_wide`` (serve every app in the tenant) and ``app_scopes`` (extra
apps beyond the home ``app_id``) to ``orchestration.provider_connections``.
Existing rows stay home-app-only (``tenant_wide=false``, ``app_scopes='{}'``).

Revision ID: 0094
Revises: 0093
Create Date: 2026-06-09
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0094"
down_revision: Union[str, None] = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_connections",
        sa.Column("tenant_wide", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="orchestration",
    )
    op.add_column(
        "provider_connections",
        sa.Column(
            "app_scopes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        schema="orchestration",
    )
    op.create_index(
        "idx_provider_connections_app_scopes",
        "provider_connections",
        ["app_scopes"],
        unique=False,
        postgresql_using="gin",
        schema="orchestration",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_provider_connections_app_scopes",
        table_name="provider_connections",
        schema="orchestration",
    )
    op.drop_column("provider_connections", "app_scopes", schema="orchestration")
    op.drop_column("provider_connections", "tenant_wide", schema="orchestration")
