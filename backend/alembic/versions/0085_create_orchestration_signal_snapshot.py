"""orchestration_signal_snapshot — per-(tenant, app) orchestration-signal snapshots.

Stores the latest LLM-generated orchestration-signal snapshot per (tenant, app);
the analytics dashboard reads the most recent row. Populated by a scheduled
generator job; the read endpoint returns empty until then.

Revision ID: 0085
Revises: 0084
Create Date: 2026-05-29
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0085"
down_revision: Union[str, None] = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_signal_snapshot",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
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
        "ix_orchestration_signal_snapshot_recent",
        "orchestration_signal_snapshot",
        ["tenant_id", "app_id", sa.text("generated_at DESC")],
        schema="analytics",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orchestration_signal_snapshot_recent",
        table_name="orchestration_signal_snapshot",
        schema="analytics",
    )
    op.drop_table("orchestration_signal_snapshot", schema="analytics")
