"""workflow engagement analytics — flat fact_workflow_engagement + agg_workflow_run matview.

ADDITIVE (Leg 2 Phase 1): creates the dispatch analytics fact (one row per run × recipient ×
capability) and a per-run rollup MATERIALIZED VIEW that collapses each recipient to ONE
most-advanced bucket across capabilities. Both written/rebuilt by the one populator. No TXN change.

Revision ID: 0090
Revises: 0089
Create Date: 2026-06-03
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0090"
down_revision: Union[str, None] = "0089"
branch_labels = None
depends_on = None


# Recipient-collapsed run rollup: rank buckets (positive=1 … in_flight=5), take the most-advanced
# (MIN rank) per recipient across capabilities, then count recipients per bucket per run.
AGG_MATVIEW_SQL = """
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


def upgrade() -> None:
    op.create_table(
        "fact_workflow_engagement",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_name", sa.Text(), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_id", sa.String(length=128), nullable=False),
        sa.Column("lead_id", sa.String(length=128), nullable=True),  # == dim_lead.lead_id (varchar)
        sa.Column("contact_e164", sa.Text(), nullable=True),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("connection_label", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("outcome_bucket", sa.String(length=16), nullable=False),
        sa.Column("dispatched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_sec", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("talk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("provider_status", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=16), nullable=True),
        sa.Column("run_status", sa.String(length=16), nullable=True),
        sa.Column("cohort_size_at_entry", sa.Integer(), nullable=True),
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "recipient_id", "capability", name="uq_fwe_run_recipient_capability"),
        schema="analytics",
    )
    op.create_index("idx_fwe_tenant_app", "fact_workflow_engagement", ["tenant_id", "app_id"], schema="analytics")
    op.create_index("idx_fwe_app_workflow_started", "fact_workflow_engagement",
                    ["app_id", "workflow_id", "run_started_at"], schema="analytics")
    op.create_index("idx_fwe_app_channel_started", "fact_workflow_engagement",
                    ["app_id", "channel", "run_started_at"], schema="analytics")
    op.create_index("idx_fwe_run", "fact_workflow_engagement", ["run_id"], schema="analytics")
    op.create_index("idx_fwe_app_recipient", "fact_workflow_engagement", ["app_id", "recipient_id"], schema="analytics")
    op.create_index("idx_fwe_app_lead", "fact_workflow_engagement", ["app_id", "lead_id"], schema="analytics")

    op.execute(AGG_MATVIEW_SQL)
    op.execute("CREATE UNIQUE INDEX idx_agg_workflow_run_run ON analytics.agg_workflow_run (run_id)")
    op.execute("CREATE INDEX idx_agg_workflow_run_tenant_app ON analytics.agg_workflow_run (tenant_id, app_id)")
    op.execute("CREATE INDEX idx_agg_workflow_run_app_workflow ON analytics.agg_workflow_run (app_id, workflow_id)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.agg_workflow_run")
    op.drop_table("fact_workflow_engagement", schema="analytics")
