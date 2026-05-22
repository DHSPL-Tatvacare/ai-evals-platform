"""choke table is membership-only: nullable phone/predicate, add ingress_kind + provenance

Revision ID: 0075
Revises: 0074
Create Date: 2026-05-22

The single ingress choke table orchestration.workflow_run_recipients records
membership only — "is this recipient real for this run". Its phone_e164 is
best-effort provenance, NOT the dispatch destination and NOT the reach-count
key, so dataset / event ingress (which may have no resolvable phone at T0)
can still register and assert_recipient_in_manifest passes for them.
phone_e164 and predicate_hash become nullable; ingress_kind + provenance are
added. Backward-compatible (nullable / defaulted) for the shared docker DB.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0075"
down_revision: Union[str, None] = "0074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE orchestration.workflow_run_recipients
            ALTER COLUMN phone_e164 DROP NOT NULL,
            ALTER COLUMN predicate_hash DROP NOT NULL,
            ADD COLUMN IF NOT EXISTS ingress_kind VARCHAR(32),
            ADD COLUMN IF NOT EXISTS provenance JSONB
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE orchestration.workflow_run_recipients
            DROP COLUMN IF EXISTS provenance,
            DROP COLUMN IF EXISTS ingress_kind,
            ALTER COLUMN predicate_hash SET NOT NULL,
            ALTER COLUMN phone_e164 SET NOT NULL
        """
    )
