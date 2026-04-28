"""move 16 analytics-adjacent tables from public to analytics schema

Roadmap 01 §9.3 + §3.2 revision 0008. Pure ``ALTER TABLE ... SET SCHEMA``
moves — no renames yet, no column changes. The renames land in
revision 0009 and the legacy ``evaluation_analytics`` cache drop lands
in 0010.

Tables moved (16):
  - analytics_run_facts, analytics_eval_facts, analytics_criterion_facts
  - analytics_jobs, agent_tool_logs, analytics_query_cache
  - source_call_records, source_lead_records, source_sync_runs
  - llm_usage, llm_usage_daily_rollup
  - model_pricing, model_aliases
  - models_dev_catalog, models_dev_snapshots
  - evaluation_analytics

After this revision, ``public`` holds only ``alembic_version`` (per
plan §1 / §17). The ``analytics_charts`` and ``analytics_dashboards``
tables stay in ``platform`` (already moved by 0006) — they are
user-owned config, not analytics facts (§3.4 judgement call).

``ALTER TABLE ... SET SCHEMA`` is metadata-only; FKs are preserved by
Postgres across the move (cross-schema FKs work natively). Whole
revision is one transactional unit.

Reversibility: downgrade reverses every move (``analytics.X SET SCHEMA
public``). Symmetric.

Revision ID: 0008_move_analytics_tables_to_analytics
Revises: 0007_create_analytics_schema_and_role
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0008_move_analytics_tables_to_analytics"
down_revision: Union[str, None] = "0007_create_analytics_schema_and_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 16 analytics-adjacent tables. Order doesn't matter — SET SCHEMA preserves
# FK constraints; the transactional wrapping makes the whole move atomic.
_TABLES_TO_MOVE: tuple[str, ...] = (
    # Analytics fact / aggregate tables
    "analytics_run_facts",
    "analytics_eval_facts",
    "analytics_criterion_facts",
    # Analytics logs / cache
    "analytics_jobs",
    "agent_tool_logs",
    "analytics_query_cache",
    # CRM source mirror
    "source_call_records",
    "source_lead_records",
    "source_sync_runs",
    # LLM cost / observability
    "llm_usage",
    "llm_usage_daily_rollup",
    "model_pricing",
    "model_aliases",
    "models_dev_catalog",
    "models_dev_snapshots",
    # Legacy single/cross-run cache (dropped in 0010)
    "evaluation_analytics",
)


def upgrade() -> None:
    assert len(_TABLES_TO_MOVE) == 16, (
        f"expected 16 tables to move per plan §3.2 + §3.3, got {len(_TABLES_TO_MOVE)}"
    )
    for table in _TABLES_TO_MOVE:
        op.execute(f"ALTER TABLE public.{table} SET SCHEMA analytics")


def downgrade() -> None:
    for table in _TABLES_TO_MOVE:
        op.execute(f"ALTER TABLE analytics.{table} SET SCHEMA public")
