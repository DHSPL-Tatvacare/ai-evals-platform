"""unify evaluation analytics — flat fact_evaluation + fact_evaluation_review + agg matview.

Drops the old JSON-bearing fact_evaluation / fact_evaluation_criterion / agg_evaluation_run
(table) and replaces them with two flat leaf facts plus a per-run rollup MATERIALIZED VIEW
rebuilt by the one populator. Clean move, no shim.

Revision ID: 0089
Revises: 0088
Create Date: 2026-06-03
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0089"
down_revision: Union[str, None] = "0088"
branch_labels = None
depends_on = None


AGG_MATVIEW_SQL = """
CREATE MATERIALIZED VIEW analytics.agg_evaluation_run AS
WITH per_target AS (
    SELECT
        f.run_id,
        f.target_key,
        bool_or(f.style = 'rule' AND f.status = 'FAIL') AS has_rule_fail,
        bool_or(f.severity = 'critical') AS has_critical,
        avg(f.score) FILTER (WHERE f.is_main) AS main_score
    FROM analytics.fact_evaluation f
    GROUP BY f.run_id, f.target_key
),
per_run AS (
    SELECT
        run_id,
        count(*) FILTER (WHERE style = 'rule' AND status = 'FAIL') AS rule_fail_count,
        count(*) FILTER (WHERE severity = 'critical') AS critical_count
    FROM analytics.fact_evaluation
    GROUP BY run_id
)
SELECT
    r.id AS run_id,
    r.app_id,
    r.eval_type,
    r.tenant_id,
    r.user_id,
    r.status,
    r.created_at,
    r.completed_at,
    r.duration_ms,
    NULLIF(r.batch_metadata ->> 'name', '') AS run_name,
    count(pt.target_key) AS thread_count,
    count(pt.target_key) FILTER (WHERE NOT pt.has_rule_fail AND NOT pt.has_critical) AS pass_count,
    count(pt.target_key) FILTER (WHERE pt.has_rule_fail OR pt.has_critical) AS fail_count,
    CASE WHEN count(pt.target_key) > 0
         THEN round(
             (count(pt.target_key) FILTER (WHERE NOT pt.has_rule_fail AND NOT pt.has_critical))::numeric
             / count(pt.target_key), 4)
         ELSE NULL END AS pass_rate,
    avg(pt.main_score) AS avg_score,
    coalesce(pr.rule_fail_count, 0) AS rule_fail_count,
    coalesce(pr.critical_count, 0) AS critical_count
FROM per_target pt
JOIN platform.evaluation_runs r ON r.id = pt.run_id
LEFT JOIN per_run pr ON pr.run_id = pt.run_id
GROUP BY r.id, pr.rule_fail_count, pr.critical_count
"""


def upgrade() -> None:
    # 1. Drop the old analytics relations (clean move).
    op.execute("DROP TABLE IF EXISTS analytics.fact_evaluation_criterion CASCADE")
    op.execute("DROP TABLE IF EXISTS analytics.fact_evaluation CASCADE")
    op.execute("DROP TABLE IF EXISTS analytics.agg_evaluation_run CASCADE")

    # 2. Flat leaf fact — one row per platform.evaluation_details.
    op.create_table(
        "fact_evaluation",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True, nullable=False),
        sa.Column("detail_id", sa.BigInteger(), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("app_id", sa.Text(), nullable=False),
        sa.Column("eval_type", sa.Text(), nullable=False),
        sa.Column("run_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("evaluator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluator_name", sa.Text(), nullable=True),
        sa.Column("style", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("max", sa.Numeric(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("candidate_text", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        schema="analytics",
    )
    op.create_index("idx_fe_run", "fact_evaluation", ["run_id"], schema="analytics")
    op.create_index("idx_fe_tenant_app", "fact_evaluation", ["tenant_id", "app_id"], schema="analytics")
    op.create_index("idx_fe_app_type_style_key", "fact_evaluation",
                    ["app_id", "eval_type", "style", "key"], schema="analytics")
    op.create_index("idx_fe_app_lead", "fact_evaluation", ["app_id", "lead_id"], schema="analytics")
    op.create_index("idx_fe_detail", "fact_evaluation", ["detail_id"], unique=True, schema="analytics")

    # 3. Flat review fact — one row per platform.evaluation_review_items.
    op.create_table(
        "fact_evaluation_review",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True, nullable=False),
        sa.Column("review_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.Text(), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=True),
        sa.Column("overall_decision", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("reviewed_value", sa.Text(), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        schema="analytics",
    )
    op.create_index("idx_fer_run_key", "fact_evaluation_review", ["run_id", "key"], schema="analytics")
    op.create_index("idx_fer_app_key", "fact_evaluation_review", ["app_id", "key"], schema="analytics")
    op.create_index("idx_fer_tenant_app", "fact_evaluation_review", ["tenant_id", "app_id"], schema="analytics")
    op.create_index("idx_fer_item", "fact_evaluation_review", ["review_item_id"], unique=True, schema="analytics")

    # 4. Per-run rollup matview, rebuilt by the populator. Unique index on run_id
    #    enables REFRESH ... CONCURRENTLY and run-keyed joins.
    op.execute(AGG_MATVIEW_SQL)
    op.execute("CREATE UNIQUE INDEX idx_agg_evaluation_run_run ON analytics.agg_evaluation_run (run_id)")
    op.execute("CREATE INDEX idx_agg_evaluation_run_tenant_app ON analytics.agg_evaluation_run (tenant_id, app_id)")
    op.execute("CREATE INDEX idx_agg_evaluation_run_app_type ON analytics.agg_evaluation_run (app_id, eval_type)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.agg_evaluation_run")
    op.drop_table("fact_evaluation_review", schema="analytics")
    op.drop_table("fact_evaluation", schema="analytics")
