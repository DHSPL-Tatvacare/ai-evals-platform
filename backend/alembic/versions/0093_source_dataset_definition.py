"""source dataset definition — per-dataset ingestion definition (filter + lifecycle).

One row per tenant+app+connection+record_type. ``connection_id`` is an indexed UUID,
NOT a cross-schema FK (links go orchestration→platform; app code scopes on
tenant+app+connection). The field map stays in ``crm_field_map``.

Revision ID: 0093
Revises: 0092
Create Date: 2026-06-09
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0093"
down_revision: Union[str, None] = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_dataset_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("filter_predicate", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "record_type",
            name="uq_source_dataset_definition_scope",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_source_dataset_definition_scope", "source_dataset_definition",
        ["tenant_id", "app_id", "connection_id"], schema="platform",
    )


def downgrade() -> None:
    op.drop_table("source_dataset_definition", schema="platform")
