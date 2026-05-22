"""drop vendor correlation columns, add generic provider_reply_ref

Revision ID: 0074
Revises: 0073
Create Date: 2026-05-22

One generic correlation contract on orchestration.workflow_run_recipient_actions:
``provider_correlation_id`` (send-time id, all providers, status/outcome) already
exists from 0027. The vendor-named ``bolna_execution_id`` / ``bolna_batch_id`` are
redundant (provider_correlation_id holds the execution_id/batch_id) and never read
on a live path — drop them. Add ``provider_reply_ref`` for the id an inbound reply
quotes (WhatsApp WAMID; null for voice), with a partial index for reply lookup.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0074"
down_revision: Union[str, None] = "0073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS orchestration.idx_workflow_run_recipient_actions_open_bolna"
    )
    op.execute(
        """
        ALTER TABLE orchestration.workflow_run_recipient_actions
            DROP COLUMN IF EXISTS bolna_execution_id,
            DROP COLUMN IF EXISTS bolna_batch_id,
            ADD COLUMN provider_reply_ref VARCHAR(128)
        """
    )
    op.execute(
        "CREATE INDEX idx_orch_actions_provider_reply_ref "
        "ON orchestration.workflow_run_recipient_actions "
        "(provider_reply_ref) "
        "WHERE provider_reply_ref IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS orchestration.idx_orch_actions_provider_reply_ref"
    )
    op.execute(
        """
        ALTER TABLE orchestration.workflow_run_recipient_actions
            DROP COLUMN IF EXISTS provider_reply_ref,
            ADD COLUMN bolna_execution_id VARCHAR(128),
            ADD COLUMN bolna_batch_id     VARCHAR(128)
        """
    )
    op.execute(
        "CREATE INDEX idx_workflow_run_recipient_actions_open_bolna "
        "ON orchestration.workflow_run_recipient_actions "
        "(bolna_execution_id, bolna_batch_id) "
        "WHERE completed_at IS NULL "
        "AND channel = 'bolna' "
        "AND (bolna_execution_id IS NOT NULL OR bolna_batch_id IS NOT NULL)"
    )
