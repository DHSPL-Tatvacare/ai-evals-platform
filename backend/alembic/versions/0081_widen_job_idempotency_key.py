"""platform: widen background_jobs.idempotency_key to 255

Revision ID: 0081
Revises: 0080
Create Date: 2026-05-26

Per-recipient resume keys (run-resume:{run_id}:{recipient}:voice-outcome|{exec_id}|
{outcome}) exceed the original varchar(120) and crash the reconciler with a
StringDataRightTruncationError, rolling back the whole reconcile transaction.
Widen to 255; every existing key fits, so no data migration is needed.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0081"
down_revision: Union[str, None] = "0080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE platform.background_jobs "
        "ALTER COLUMN idempotency_key TYPE varchar(255)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE platform.background_jobs "
        "ALTER COLUMN idempotency_key TYPE varchar(120)"
    )
