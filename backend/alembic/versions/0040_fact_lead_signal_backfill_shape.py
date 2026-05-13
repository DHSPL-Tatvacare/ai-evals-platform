"""phase 5 - fact_lead_signal shape for non-eval (backfill / extraction) writes

Revision ID: 0040_fact_lead_signal_backfill_shape
Revises: 0039_analytics_mapping_state
Create Date: 2026-05-14

Phase 5 of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

The original plan claimed "schema unchanged" for ``analytics.fact_lead_signal``
but the live table required NOT NULL ``eval_run_id`` + ``thread_evaluation_id``
FKs (eval-run-coupled writes only). Phase 5 backfill walks the CRM lead mirror
which has no eval-run lineage, so this revision makes those two columns
nullable and adds the rollback / idempotency surface the plan describes:

* ``sync_run_id`` FK to ``analytics.log_crm_source_sync(id)`` (ON DELETE SET
  NULL) — every backfill row carries the run id so rollback is one DELETE.
* ``detected_at timestamptz`` — observation timestamp used in the partial
  unique key. Distinct from ``signal_at`` (which is the source-side moment of
  the signal as reported by the extractor).
* Partial unique index ``uq_fact_lead_signal_backfill (tenant_id, app_id,
  lead_id, signal_type, detected_at) WHERE sync_run_id IS NOT NULL`` — makes
  backfill rerun idempotent without disturbing the existing eval-run-coupled
  unique constraint.
* Btree ``(tenant_id, app_id, sync_run_id)`` — powers the rollback DELETE.

Existing eval-run-coupled rows are untouched. Schema-qualifies every raw SQL
statement per the Roadmap 01 invariant.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0040_fact_lead_signal_backfill_shape"
down_revision: Union[str, None] = "0039_analytics_mapping_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "fact_lead_signal",
        "eval_run_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
        schema="analytics",
    )
    op.alter_column(
        "fact_lead_signal",
        "thread_evaluation_id",
        existing_type=sa.Integer(),
        nullable=True,
        schema="analytics",
    )

    op.add_column(
        "fact_lead_signal",
        sa.Column(
            "sync_run_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "analytics.log_crm_source_sync.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        schema="analytics",
    )
    op.add_column(
        "fact_lead_signal",
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="analytics",
    )

    op.create_index(
        "ix_fact_lead_signal_tenant_app_sync_run",
        "fact_lead_signal",
        ["tenant_id", "app_id", "sync_run_id"],
        schema="analytics",
    )

    # Partial unique index covers ONLY backfill rows. Eval-run-coupled rows
    # (sync_run_id IS NULL) fall under the existing
    # uq_fact_lead_signal_run_thread_signal constraint and are unaffected.
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_fact_lead_signal_backfill
            ON analytics.fact_lead_signal (
                tenant_id, app_id, lead_id, signal_type, detected_at
            )
            WHERE sync_run_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP INDEX IF EXISTS analytics.uq_fact_lead_signal_backfill")
    )
    op.drop_index(
        "ix_fact_lead_signal_tenant_app_sync_run",
        table_name="fact_lead_signal",
        schema="analytics",
    )
    op.drop_column("fact_lead_signal", "detected_at", schema="analytics")
    op.drop_column("fact_lead_signal", "sync_run_id", schema="analytics")
    op.alter_column(
        "fact_lead_signal",
        "thread_evaluation_id",
        existing_type=sa.Integer(),
        nullable=False,
        schema="analytics",
    )
    op.alter_column(
        "fact_lead_signal",
        "eval_run_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
        schema="analytics",
    )
