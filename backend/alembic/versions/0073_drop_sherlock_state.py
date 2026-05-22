"""drop platform.sherlock_state — dead cross-turn-state plumbing

Revision ID: 0073
Revises: 0072
Create Date: 2026-05-21

``platform.sherlock_state`` (added by 0035) was DORMANT: no producer ever
wrote a row. Cross-turn memory uses the ``previous_response_id`` chain on
``platform.sherlock_agent_sessions`` instead. The read path and ORM model
are removed, so the table goes too. ``sherlock_evidence`` is untouched.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0073"
down_revision: Union[str, None] = "0072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "idx_sherlock_state_tenant_user_app",
        table_name="sherlock_state",
        schema="platform",
    )
    op.drop_table("sherlock_state", schema="platform")


def downgrade() -> None:
    op.create_table(
        "sherlock_state",
        sa.Column(
            "chat_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.chat_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("app_id", sa.Text(), nullable=False),
        sa.Column(
            "resolved_entities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "active_filters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "last_specialist_call_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="platform",
    )
    op.create_index(
        "idx_sherlock_state_tenant_user_app",
        "sherlock_state",
        ["tenant_id", "user_id", "app_id"],
        schema="platform",
    )
