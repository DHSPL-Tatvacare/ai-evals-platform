"""phase 1 — rename agent_*->rep_*, prospect_id->lead_id; add fact/dim cols + uq index; legacy views

Revision ID: 0038_rename_crm_columns_and_fact_dim_adds
Revises: 0037_tenant_config_sherlock_instructions
Create Date: 2026-05-13

Phase 1 of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

Renames-first PR that canonicalizes CRM mirror naming and adds the
fact/dim schema downstream phases depend on:

  * ``analytics.crm_call_record``  rename ``agent_id|agent_name|agent_email`` to ``rep_*``
                                   rename ``prospect_id`` to ``lead_id``
  * ``analytics.crm_lead_record``  rename ``prospect_id`` to ``lead_id``
  * ``analytics.fact_lead_activity`` add ``actor_label text``
                                     drop old ``uq_fact_lead_activity_tenant_app_source``
                                     create ``uq_fact_lead_activity_source`` CONCURRENTLY
                                       on ``(tenant_id, app_id, source_activity_id, activity_type)``
  * ``analytics.dim_lead``         add ``attributes jsonb``
                                   add ``assigned_rep_label text``
  * Legacy views ``analytics.crm_call_record_legacy`` /
    ``analytics.crm_lead_record_legacy`` per Appendix A.8 (dropped in
    Phase 9 after soak).

Schema-qualifies every raw SQL statement (Roadmap 01 §9.6 invariant);
runs the Appendix A.6 preflight before the unique index is created so a
non-empty duplicate set aborts with a precise diagnostic instead of
leaving partial state.

CREATE UNIQUE INDEX CONCURRENTLY runs inside ``autocommit_block()`` —
Postgres rejects it inside a transaction, and Alembic's env.py wraps the
whole revision in ``context.begin_transaction()``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0038_rename_crm_columns_and_fact_dim_adds"
down_revision: Union[str, None] = "0037_tenant_config_sherlock_instructions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── helpers ────────────────────────────────────────────────────────────


def _preflight_duplicates(bind) -> None:
    """Appendix A.6: refuse to create unique structures over duplicate keys.

    Both checks are cheap (uses indexed columns). Aborting here is strictly
    better than letting CREATE UNIQUE INDEX CONCURRENTLY fail mid-build and
    leave an INVALID index on a prod table.
    """
    # Existing ``uq_crm_call_record_tenant_app_activity`` already enforces
    # this set — the check is in the appendix as a belt-and-braces guard,
    # and stays here for the same reason.
    rows = bind.execute(
        sa.text(
            """
            SELECT tenant_id, app_id, activity_id, COUNT(*) AS n
            FROM analytics.crm_call_record
            GROUP BY tenant_id, app_id, activity_id
            HAVING COUNT(*) > 1
            LIMIT 10
            """
        )
    ).fetchall()
    if rows:
        raise RuntimeError(
            "preflight failed: analytics.crm_call_record has duplicate "
            f"(tenant_id, app_id, activity_id) keys; sample: {[tuple(r) for r in rows]}"
        )

    rows = bind.execute(
        sa.text(
            """
            SELECT tenant_id, app_id, source_activity_id, activity_type, COUNT(*) AS n
            FROM analytics.fact_lead_activity
            GROUP BY tenant_id, app_id, source_activity_id, activity_type
            HAVING COUNT(*) > 1
            LIMIT 10
            """
        )
    ).fetchall()
    if rows:
        raise RuntimeError(
            "preflight failed: analytics.fact_lead_activity has duplicate "
            "(tenant_id, app_id, source_activity_id, activity_type) keys; "
            f"sample: {[tuple(r) for r in rows]}. Resolve duplicates before "
            "re-running this migration."
        )


# ── upgrade ────────────────────────────────────────────────────────────


def upgrade() -> None:
    bind = op.get_bind()

    # Preflight runs first. If it raises, the surrounding transaction
    # rolls back before any DDL is emitted.
    _preflight_duplicates(bind)

    # Mirror column renames. ``RENAME COLUMN`` updates dependent index
    # definitions and the unique-constraint column lists in place, so the
    # existing indexes (``idx_crm_call_record_tenant_app_prospect``,
    # ``idx_crm_call_record_tenant_app_agent_lower``, etc.) stay valid
    # under their original names but with the new column references.
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN agent_id TO rep_id"
    )
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN agent_name TO rep_name"
    )
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN agent_email TO rep_email"
    )
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN prospect_id TO lead_id"
    )

    op.execute(
        "ALTER TABLE analytics.crm_lead_record RENAME COLUMN prospect_id TO lead_id"
    )
    op.execute(
        "ALTER TABLE analytics.crm_lead_record RENAME COLUMN agent_name TO rep_name"
    )

    # Fact additions.
    op.add_column(
        "fact_lead_activity",
        sa.Column("actor_label", sa.Text(), nullable=True),
        schema="analytics",
    )

    # The old unique constraint enforces uniqueness on
    # ``(tenant_id, app_id, source_activity_id)``. The new contract widens
    # the key with ``activity_type`` so multiple CRM apps can map their
    # ``call`` / ``email`` / ``custom`` activities into the same fact
    # table without colliding on ``source_activity_id`` namespaces.
    op.execute(
        "ALTER TABLE analytics.fact_lead_activity "
        "DROP CONSTRAINT IF EXISTS uq_fact_lead_activity_tenant_app_source"
    )

    # Dim additions.
    op.add_column(
        "dim_lead",
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            nullable=True,
        ),
        schema="analytics",
    )
    op.add_column(
        "dim_lead",
        sa.Column("assigned_rep_label", sa.Text(), nullable=True),
        schema="analytics",
    )

    # Legacy views (Appendix A.8). Created before the CONCURRENTLY block
    # so they live in the same transaction as the renames.
    op.execute(
        """
        CREATE VIEW analytics.crm_call_record_legacy AS
        SELECT
          c.*,
          c.rep_id    AS agent_id,
          c.rep_name  AS agent_name,
          c.rep_email AS agent_email,
          c.lead_id   AS prospect_id
        FROM analytics.crm_call_record AS c
        """
    )
    op.execute(
        """
        CREATE VIEW analytics.crm_lead_record_legacy AS
        SELECT
          l.*,
          l.lead_id  AS prospect_id,
          l.rep_name AS agent_name
        FROM analytics.crm_lead_record AS l
        """
    )

    # CREATE UNIQUE INDEX CONCURRENTLY cannot run inside a transaction.
    # ``autocommit_block`` commits whatever Alembic was holding open,
    # runs the body with the connection in AUTOCOMMIT, then resumes the
    # outer transaction (which is empty here — this is the last DDL).
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            "uq_fact_lead_activity_source "
            "ON analytics.fact_lead_activity "
            "(tenant_id, app_id, source_activity_id, activity_type)"
        )


# ── downgrade ──────────────────────────────────────────────────────────


def downgrade() -> None:
    # Drop the wider unique index in autocommit (it was created concurrently).
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "analytics.uq_fact_lead_activity_source"
        )

    # Recreate the prior constraint so ORM expectations are preserved on
    # downgrade. Same columns as before Phase 1.
    op.execute(
        "ALTER TABLE analytics.fact_lead_activity "
        "ADD CONSTRAINT uq_fact_lead_activity_tenant_app_source "
        "UNIQUE (tenant_id, app_id, source_activity_id)"
    )

    # Views first — they reference the post-rename column names.
    op.execute("DROP VIEW IF EXISTS analytics.crm_lead_record_legacy")
    op.execute("DROP VIEW IF EXISTS analytics.crm_call_record_legacy")

    # Dim additions.
    op.drop_column("dim_lead", "assigned_rep_label", schema="analytics")
    op.drop_column("dim_lead", "attributes", schema="analytics")

    # Fact additions.
    op.drop_column("fact_lead_activity", "actor_label", schema="analytics")

    # Mirror renames (reverse order — doesn't matter for renames, but stays
    # symmetric with upgrade).
    op.execute(
        "ALTER TABLE analytics.crm_lead_record RENAME COLUMN rep_name TO agent_name"
    )
    op.execute(
        "ALTER TABLE analytics.crm_lead_record RENAME COLUMN lead_id TO prospect_id"
    )

    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN lead_id TO prospect_id"
    )
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN rep_email TO agent_email"
    )
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN rep_name TO agent_name"
    )
    op.execute(
        "ALTER TABLE analytics.crm_call_record RENAME COLUMN rep_id TO agent_id"
    )
