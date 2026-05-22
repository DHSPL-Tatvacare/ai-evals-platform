"""per-trigger webhook token + vendor on workflow_triggers, event ingest dedupe log

Revision ID: 0077
Revises: 0076
Create Date: 2026-05-23

Model A multi-tenant event triggers: each event trigger carries a unique
webhook_token (one token resolves exactly one trigger → one workflow + tenant)
and a vendor whose native payload it ingests. Existing event triggers are
backfilled with a generated token + vendor='webhook'. The event_ingest_log
table is the replay-dedupe ledger so a CRM retry never creates a second run.
"""
from __future__ import annotations

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0077"
down_revision: Union[str, None] = "0076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE orchestration.workflow_triggers
            ADD COLUMN IF NOT EXISTS webhook_token VARCHAR(64),
            ADD COLUMN IF NOT EXISTS vendor VARCHAR(64) NOT NULL DEFAULT 'webhook'
        """
    )

    # Backfill: every existing event trigger gets a generated token + webhook vendor.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id FROM orchestration.workflow_triggers "
            "WHERE kind = 'event' AND webhook_token IS NULL"
        )
    ).fetchall()
    for (trigger_id,) in rows:
        bind.execute(
            sa.text(
                "UPDATE orchestration.workflow_triggers "
                "SET webhook_token = :tok, vendor = COALESCE(vendor, 'webhook') "
                "WHERE id = :id"
            ),
            {"tok": secrets.token_urlsafe(32), "id": trigger_id},
        )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_triggers_webhook_token
            ON orchestration.workflow_triggers (webhook_token)
            WHERE webhook_token IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS orchestration.event_ingest_log (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES platform.tenants(id) ON DELETE CASCADE,
            app_id VARCHAR(64) NOT NULL,
            trigger_id UUID NOT NULL REFERENCES orchestration.workflow_triggers(id) ON DELETE CASCADE,
            ingest_key VARCHAR(256) NOT NULL,
            run_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_event_ingest_log_trigger_key
            ON orchestration.event_ingest_log (trigger_id, ingest_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_ingest_log_tenant_created
            ON orchestration.event_ingest_log (tenant_id, created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS orchestration.event_ingest_log")
    op.execute(
        "DROP INDEX IF EXISTS orchestration.uq_workflow_triggers_webhook_token"
    )
    op.execute(
        """
        ALTER TABLE orchestration.workflow_triggers
            DROP COLUMN IF EXISTS webhook_token,
            DROP COLUMN IF EXISTS vendor
        """
    )
