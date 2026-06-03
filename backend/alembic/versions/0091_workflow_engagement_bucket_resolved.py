"""workflow engagement — bucket_resolved discriminator + regated agg_workflow_run matview.

Phase-3 parity fix: a pure-dispatch recipient (only dispatch markers, no terminal bucket) keeps the
``in_flight`` sentinel on the leaf fact for integrity, but ``bucket_resolved=False`` so the rollup
leaves it uncounted in every bucket — reproducing ``read_service``'s rank-0 → None semantics
(``overview.in_flight`` stays 0; the recipient still counts in ``recipients``). A genuine
``in_flight`` (explicit TXN bucket, rank≥1) is ``bucket_resolved=True`` and still counts.

Revision ID: 0091
Revises: 0090
Create Date: 2026-06-03
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0091"
down_revision: Union[str, None] = "0090"
branch_labels = None
depends_on = None


# Recipient-collapsed run rollup: most-advanced bucket among RESOLVED rows only (MIN rank over
# bucket_resolved rows); a recipient with no resolved rows yields rep_bucket NULL → counted in
# `recipients`, uncounted in every bucket filter (read_service rank-0 parity).
AGG_MATVIEW_SQL = """
CREATE MATERIALIZED VIEW analytics.agg_workflow_run AS
WITH per_recipient AS (
    SELECT
        run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
        triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at,
        recipient_id,
        (ARRAY['positive','reached','no_response','failed','in_flight'])[
            MIN(CASE WHEN bucket_resolved THEN
                    CASE outcome_bucket
                        WHEN 'positive' THEN 1 WHEN 'reached' THEN 2 WHEN 'no_response' THEN 3
                        WHEN 'failed' THEN 4 WHEN 'in_flight' THEN 5 ELSE 6 END
                ELSE NULL END)
        ] AS rep_bucket,
        bool_or(dispatched) AS dispatched,
        SUM(cost) AS cost
    FROM analytics.fact_workflow_engagement
    GROUP BY run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
             triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at, recipient_id
)
SELECT
    run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
    triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at,
    COUNT(*) AS recipients,
    COUNT(*) FILTER (WHERE rep_bucket = 'positive') AS positive,
    COUNT(*) FILTER (WHERE rep_bucket = 'reached') AS reached,
    COUNT(*) FILTER (WHERE rep_bucket = 'no_response') AS no_response,
    COUNT(*) FILTER (WHERE rep_bucket = 'failed') AS failed,
    COUNT(*) FILTER (WHERE rep_bucket = 'in_flight') AS in_flight,
    COUNT(*) FILTER (WHERE dispatched) AS dispatched,
    COALESCE(SUM(cost), 0) AS cost
FROM per_recipient
GROUP BY run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
         triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at
"""

# 0090's matview (ungated, in_flight from the populator default) — restored on downgrade.
AGG_MATVIEW_SQL_0090 = """
CREATE MATERIALIZED VIEW analytics.agg_workflow_run AS
WITH per_recipient AS (
    SELECT
        run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
        triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at,
        recipient_id,
        (ARRAY['positive','reached','no_response','failed','in_flight'])[
            MIN(CASE outcome_bucket
                    WHEN 'positive' THEN 1 WHEN 'reached' THEN 2 WHEN 'no_response' THEN 3
                    WHEN 'failed' THEN 4 WHEN 'in_flight' THEN 5 ELSE 6 END)
        ] AS rep_bucket,
        bool_or(dispatched) AS dispatched,
        SUM(cost) AS cost
    FROM analytics.fact_workflow_engagement
    GROUP BY run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
             triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at, recipient_id
)
SELECT
    run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
    triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at,
    COUNT(*) AS recipients,
    COUNT(*) FILTER (WHERE rep_bucket = 'positive') AS positive,
    COUNT(*) FILTER (WHERE rep_bucket = 'reached') AS reached,
    COUNT(*) FILTER (WHERE rep_bucket = 'no_response') AS no_response,
    COUNT(*) FILTER (WHERE rep_bucket = 'failed') AS failed,
    COUNT(*) FILTER (WHERE rep_bucket = 'in_flight') AS in_flight,
    COUNT(*) FILTER (WHERE dispatched) AS dispatched,
    COALESCE(SUM(cost), 0) AS cost
FROM per_recipient
GROUP BY run_id, tenant_id, app_id, workflow_id, workflow_name, workflow_version_id,
         triggered_by, run_status, cohort_size_at_entry, run_started_at, run_completed_at
"""

_MATVIEW_INDEXES = (
    "CREATE UNIQUE INDEX idx_agg_workflow_run_run ON analytics.agg_workflow_run (run_id)",
    "CREATE INDEX idx_agg_workflow_run_tenant_app ON analytics.agg_workflow_run (tenant_id, app_id)",
    "CREATE INDEX idx_agg_workflow_run_app_workflow ON analytics.agg_workflow_run (app_id, workflow_id)",
)


def upgrade() -> None:
    op.add_column(
        "fact_workflow_engagement",
        sa.Column("bucket_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="analytics",
    )
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.agg_workflow_run")
    op.execute(AGG_MATVIEW_SQL)
    for idx in _MATVIEW_INDEXES:
        op.execute(idx)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.agg_workflow_run")
    op.execute(AGG_MATVIEW_SQL_0090)
    for idx in _MATVIEW_INDEXES:
        op.execute(idx)
    op.drop_column("fact_workflow_engagement", "bucket_resolved", schema="analytics")
