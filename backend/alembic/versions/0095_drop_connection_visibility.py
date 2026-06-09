"""drop visibility from provider connections only

Removes the private/shared sharing concept from ``orchestration.provider_connections``:
runtime resolution never read it, the admin surface is already permission-gated,
and creator-only edit orphaned shared rows once the creator was deleted. The
other 12 ShareableMixin tables keep their visibility columns untouched.

Revision ID: 0095
Revises: 0094
Create Date: 2026-06-09
"""
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels = None
depends_on = None


_VISIBILITY_ENUM = sa.Enum("PRIVATE", "SHARED", name="asset_visibility", native_enum=False)


def upgrade() -> None:
    op.drop_index(
        "idx_provider_connections_tenant_app_visibility_active",
        table_name="provider_connections",
        schema="orchestration",
    )
    op.drop_column("provider_connections", "shared_at", schema="orchestration")
    op.drop_column("provider_connections", "shared_by", schema="orchestration")
    op.drop_column("provider_connections", "visibility", schema="orchestration")


def downgrade() -> None:
    op.add_column(
        "provider_connections",
        sa.Column(
            "visibility",
            _VISIBILITY_ENUM,
            nullable=False,
            server_default=sa.text("'PRIVATE'"),
        ),
        schema="orchestration",
    )
    op.add_column(
        "provider_connections",
        sa.Column(
            "shared_by",
            sa.UUID(),
            sa.ForeignKey("platform.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="orchestration",
    )
    op.add_column(
        "provider_connections",
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        schema="orchestration",
    )
    op.create_index(
        "idx_provider_connections_tenant_app_visibility_active",
        "provider_connections",
        ["tenant_id", "app_id", "visibility", "active"],
        unique=False,
        schema="orchestration",
    )
