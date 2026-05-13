"""phase 6 - fact_lead_stage_transition backfill shape (partial unique index)

Revision ID: 0041_fact_lead_stage_transition_backfill_shape
Revises: 0040_fact_lead_signal_backfill_shape
Create Date: 2026-05-14

Phase 6 of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

Adds a partial unique index covering only rows stamped by a backfill or
steady-state sync (``sync_run_id IS NOT NULL``). The steady-state writer in
``inside_sales_sync._append_lead_stage_transitions`` already stamps
``sync_run_id``; the Phase 6 backfill job does the same.

Key shape ``(tenant_id, app_id, lead_id, detected_at)`` — NOT including
``to_stage``. A lead has exactly one ``prospect_stage`` at any single
observation moment, so ``to_stage`` is functionally determined by the
other four columns. Including it in the key would break rerun semantics:
the backfill derives ``detected_at`` from the lead's stable ``created_on``
snapshot, so re-running after the lead's stage moved (e.g. QL → Payment
Received) would write a SECOND backfill row pinned to the same
``created_on`` instant with a different ``to_stage`` — producing two
contradictory "as-of-creation" observations for the same lead at the
same time. With ``to_stage`` outside the key, the rerun UPDATEs the
existing seed row's ``to_stage`` so the seed always reflects the latest
observed snapshot. Historical transitions remain the steady-state
writer's job (it emits one row per detected change, each with a distinct
``detected_at = cycle_start``).

Existing rows already in the table that pre-date sync_run_id stamping
(``sync_run_id IS NULL``) are NOT covered by this constraint and remain
unconstrained — matching the Phase 5 pattern on fact_lead_signal.

Preflight: aborts the migration loudly if any duplicate already exists for
the partial-key tuple. The five-tuple has never had a uniqueness contract
on the table, so a preflight is mandatory before CONCURRENTLY would have
silently skipped colliding rows. We use non-CONCURRENTLY because the table
is empty for inside-sales today (steady-state writer has been live for one
phase) and the lock window is sub-second.

Schema-qualifies every raw SQL statement per the Roadmap 01 invariant.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0041_fact_lead_stage_transition_backfill_shape"
down_revision: Union[str, None] = "0040_fact_lead_signal_backfill_shape"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preflight: refuse to create the unique index if duplicates already
    # exist for the partial-key tuple among rows that would be covered
    # (sync_run_id IS NOT NULL). Loud, with the offending keys printed, so
    # operators can choose between dedup + retry vs. rollback.
    bind = op.get_bind()
    dupes = bind.execute(
        sa.text(
            """
            SELECT tenant_id, app_id, lead_id, detected_at, COUNT(*) AS n
            FROM analytics.fact_lead_stage_transition
            WHERE sync_run_id IS NOT NULL
            GROUP BY 1, 2, 3, 4
            HAVING COUNT(*) > 1
            LIMIT 20
            """
        )
    ).fetchall()
    if dupes:
        raise RuntimeError(
            "0041 preflight refused: duplicate (tenant, app, lead, "
            "detected_at) tuples exist in fact_lead_stage_transition with "
            "sync_run_id IS NOT NULL. Resolve duplicates before retrying. "
            f"First {len(dupes)} offending keys: {dupes}"
        )

    # Btree (tenant, app, sync_run_id) powers the rollback DELETE.
    op.create_index(
        "ix_fact_lead_stage_transition_tenant_app_sync_run",
        "fact_lead_stage_transition",
        ["tenant_id", "app_id", "sync_run_id"],
        schema="analytics",
    )

    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_fact_lead_stage_transition_backfill
            ON analytics.fact_lead_stage_transition (
                tenant_id, app_id, lead_id, detected_at
            )
            WHERE sync_run_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS analytics.uq_fact_lead_stage_transition_backfill"
        )
    )
    op.drop_index(
        "ix_fact_lead_stage_transition_tenant_app_sync_run",
        table_name="fact_lead_stage_transition",
        schema="analytics",
    )
