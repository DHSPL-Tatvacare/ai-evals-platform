"""phase 11A - signal derivation framework

Revision ID: 0044_signal_derivation_framework
Revises: 0043_drop_crm_lead_record_typed_cols_and_legacy_views
Create Date: 2026-05-14

Phase 11A of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

Three structural changes, one revision:

1. ``analytics.signal_definition`` — tenant business config: one row per
   ``(tenant_id, app_id, signal_set)`` declaring which strategy plugin
   derives a signal set, the normalized surface it reads, and the
   strategy-specific body. Edited through an admin screen, not repo YAML.

2. ``analytics.fact_lead_signal.signal_definition_id`` — lineage for rows
   written by the scheduled ``derive-signals`` Transform. Partial unique
   index ``uq_fact_lead_signal_framework`` is the dedup key for framework
   rows (re-runs upsert in place); btree powers rollback / per-definition
   scans.

3. ``analytics.dim_lead`` lead-identity columns — ``first_name``,
   ``last_name``, ``phone``, ``email``, ``city``. dim_lead becomes the
   normalized serving surface the CRM workspace UI reads; these are
   ``pii: true`` in the manifest and masked by role. The mirror keeps its
   own copies for source fidelity.

The ``mql`` signal definition row is seeded by ``seed_all_defaults`` under
SYSTEM_TENANT_ID, not by this migration — same pattern as every other
system default.

Schema-qualifies every raw SQL statement per the Roadmap 01 invariant.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0044_signal_derivation_framework"
down_revision: Union[str, None] = (
    "0043_drop_crm_lead_record_typed_cols_and_legacy_views"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. signal_definition
    op.create_table(
        "signal_definition",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("signal_set", sa.String(length=64), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("source_surface", sa.String(length=128), nullable=False),
        sa.Column(
            "definition",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "app_id",
            "signal_set",
            name="uq_signal_definition_tenant_app_set",
        ),
        schema="analytics",
    )
    op.create_index(
        "ix_signal_definition_app_enabled",
        "signal_definition",
        ["app_id", "enabled"],
        schema="analytics",
    )

    # 2. fact_lead_signal.signal_definition_id + dedup / scan indexes
    op.add_column(
        "fact_lead_signal",
        sa.Column(
            "signal_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "analytics.signal_definition.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        schema="analytics",
    )
    op.create_index(
        "ix_fact_lead_signal_tenant_app_definition",
        "fact_lead_signal",
        ["tenant_id", "app_id", "signal_definition_id"],
        schema="analytics",
    )
    # Partial unique index covers ONLY signal-derivation-framework rows.
    # Eval-run-coupled rows (uq_fact_lead_signal_run_thread_signal) and
    # backfill rows (uq_fact_lead_signal_backfill) are unaffected.
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_fact_lead_signal_framework
            ON analytics.fact_lead_signal (
                tenant_id, app_id, lead_id, signal_type, detected_at
            )
            WHERE signal_definition_id IS NOT NULL
            """
        )
    )

    # 3. dim_lead lead-identity columns (pii: true in the manifest)
    for col in ("first_name", "last_name", "phone", "email", "city"):
        op.add_column(
            "dim_lead",
            sa.Column(col, sa.Text(), nullable=True),
            schema="analytics",
        )


def downgrade() -> None:
    for col in ("city", "email", "phone", "last_name", "first_name"):
        op.drop_column("dim_lead", col, schema="analytics")

    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS analytics.uq_fact_lead_signal_framework"
        )
    )
    op.drop_index(
        "ix_fact_lead_signal_tenant_app_definition",
        table_name="fact_lead_signal",
        schema="analytics",
    )
    op.drop_column(
        "fact_lead_signal", "signal_definition_id", schema="analytics"
    )

    op.drop_index(
        "ix_signal_definition_app_enabled",
        table_name="signal_definition",
        schema="analytics",
    )
    op.drop_table("signal_definition", schema="analytics")
