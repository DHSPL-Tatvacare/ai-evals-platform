"""add outcome_bucket to workflow_run_recipient_actions

Revision ID: 0084
Revises: 0083
Create Date: 2026-05-29
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0084"
down_revision: Union[str, None] = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_run_recipient_actions",
        sa.Column("outcome_bucket", sa.String(length=16), nullable=True),
        schema="orchestration",
    )


def downgrade() -> None:
    op.drop_column("workflow_run_recipient_actions", "outcome_bucket", schema="orchestration")
