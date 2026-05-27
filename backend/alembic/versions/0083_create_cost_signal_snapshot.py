"""cost_signal_snapshot — per-tenant LLM cost-signal snapshots.

Stores the latest LLM-generated cost-signal snapshot per tenant; the Cost
Overview AI-summary card reads the most recent row. Populated by a scheduled
generator job (lands separately); the read endpoint returns empty until then.

Revision ID: 0083
Revises: 0082
Create Date: 2026-05-27
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0083"
down_revision: Union[str, None] = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_signal_snapshot",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("period", sa.Text(), nullable=True),
        sa.Column("signals", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="analytics",
    )
    op.create_index(
        "ix_cost_signal_snapshot_tenant_recent",
        "cost_signal_snapshot",
        ["tenant_id", sa.text("generated_at DESC")],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cost_signal_snapshot_tenant_recent",
        table_name="cost_signal_snapshot",
        schema="analytics",
    )
    op.drop_table("cost_signal_snapshot", schema="analytics")
