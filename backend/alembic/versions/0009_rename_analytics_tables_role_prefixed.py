"""rename 15 analytics tables to their final role-prefixed names

Roadmap 01 §5.10–§5.13 revision 0009. After 0008 moved every
analytics-adjacent table into the ``analytics`` schema, this revision
renames each to its final ``fact_`` / ``agg_`` / ``ref_`` /
``snapshot_`` / ``log_`` / ``cache_`` / ``crm_`` form. Indexes and
constraints whose names embed the old physical name are renamed in
lockstep.

``evaluation_analytics`` is NOT renamed here — it is dropped in
revision 0010.

Renames (15):
  analytics_run_facts        -> agg_evaluation_run
  analytics_eval_facts       -> fact_evaluation
  analytics_criterion_facts  -> fact_evaluation_criterion
  analytics_jobs             -> log_fact_population_run
  agent_tool_logs            -> log_sherlock_tool_call
  analytics_query_cache      -> cache_sql_query
  source_call_records        -> crm_call_record
  source_lead_records        -> crm_lead_record
  source_sync_runs           -> log_crm_source_sync
  llm_usage                  -> fact_llm_generation
  llm_usage_daily_rollup     -> agg_llm_usage_daily
  model_pricing              -> ref_llm_model_pricing
  model_aliases              -> ref_llm_model_alias
  models_dev_catalog         -> ref_llm_models_catalog
  models_dev_snapshots       -> snapshot_llm_models_catalog

Reversibility: downgrade reverses every rename (table + indexes +
constraints) in symmetric order.

Revision ID: 0009_rename_analytics_tables_role_prefixed
Revises: 0008_move_analytics_tables_to_analytics
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0009_rename_analytics_tables_role_prefixed"
down_revision: Union[str, None] = "0008_move_analytics_tables_to_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (old_table, new_table, [(old_index_or_constraint, new_index_or_constraint), ...])
# Index / constraint renames are listed only where the original name embeds
# the old physical table name. Per-table abbreviations (idx_arf_*, idx_aef_*,
# etc.) don't embed the table name so they are not renamed.
_TABLE_RENAMES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    ("analytics_run_facts", "agg_evaluation_run", ()),
    ("analytics_eval_facts", "fact_evaluation", ()),
    ("analytics_criterion_facts", "fact_evaluation_criterion", ()),
    ("analytics_jobs", "log_fact_population_run", ()),
    ("agent_tool_logs", "log_sherlock_tool_call", ()),
    ("analytics_query_cache", "cache_sql_query", ()),
    (
        "source_call_records",
        "crm_call_record",
        (
            ("uq_source_call_records_tenant_app_activity",
             "uq_crm_call_record_tenant_app_activity"),
            ("idx_source_call_records_tenant_app_call_started",
             "idx_crm_call_record_tenant_app_call_started"),
            ("idx_source_call_records_tenant_app_created",
             "idx_crm_call_record_tenant_app_created"),
            ("idx_source_call_records_tenant_app_activity_time",
             "idx_crm_call_record_tenant_app_activity_time"),
            ("idx_source_call_records_tenant_app_agent_lower",
             "idx_crm_call_record_tenant_app_agent_lower"),
            ("idx_source_call_records_tenant_app_direction",
             "idx_crm_call_record_tenant_app_direction"),
            ("idx_source_call_records_tenant_app_status_lower",
             "idx_crm_call_record_tenant_app_status_lower"),
            ("idx_source_call_records_tenant_app_prospect",
             "idx_crm_call_record_tenant_app_prospect"),
            ("idx_source_call_records_tenant_app_recording",
             "idx_crm_call_record_tenant_app_recording"),
        ),
    ),
    (
        "source_lead_records",
        "crm_lead_record",
        (
            ("uq_source_lead_records_tenant_app_prospect",
             "uq_crm_lead_record_tenant_app_prospect"),
            ("idx_source_lead_records_tenant_app_created",
             "idx_crm_lead_record_tenant_app_created"),
            ("idx_source_lead_records_tenant_app_created_prospect",
             "idx_crm_lead_record_tenant_app_created_prospect"),
            ("idx_source_lead_records_tenant_app_last_activity",
             "idx_crm_lead_record_tenant_app_last_activity"),
            ("idx_source_lead_records_tenant_app_stage_lower",
             "idx_crm_lead_record_tenant_app_stage_lower"),
            ("idx_source_lead_records_tenant_app_agent_lower",
             "idx_crm_lead_record_tenant_app_agent_lower"),
            ("idx_source_lead_records_tenant_app_city_lower",
             "idx_crm_lead_record_tenant_app_city_lower"),
            ("idx_source_lead_records_tenant_app_mql",
             "idx_crm_lead_record_tenant_app_mql"),
            ("idx_source_lead_records_tenant_app_plan_name",
             "idx_crm_lead_record_tenant_app_plan_name"),
        ),
    ),
    (
        "source_sync_runs",
        "log_crm_source_sync",
        (
            ("fk_source_sync_runs_job_id",
             "fk_log_crm_source_sync_job_id"),
            ("idx_source_sync_runs_tenant_app_created",
             "idx_log_crm_source_sync_tenant_app_created"),
            ("idx_source_sync_runs_tenant_family_status",
             "idx_log_crm_source_sync_tenant_family_status"),
            ("idx_source_sync_runs_tenant_family_completed",
             "idx_log_crm_source_sync_tenant_family_completed"),
            ("idx_source_sync_runs_tenant_app_family_scheduled",
             "idx_log_crm_source_sync_tenant_app_family_scheduled"),
        ),
    ),
    (
        "llm_usage",
        "fact_llm_generation",
        (
            ("uq_llm_usage_idempotency_key",
             "uq_fact_llm_generation_idempotency_key"),
            ("idx_llm_usage_tenant_created",
             "idx_fact_llm_generation_tenant_created"),
            ("idx_llm_usage_tenant_app_created",
             "idx_fact_llm_generation_tenant_app_created"),
            ("idx_llm_usage_tenant_user_created",
             "idx_fact_llm_generation_tenant_user_created"),
            ("idx_llm_usage_owner",
             "idx_fact_llm_generation_owner"),
            ("idx_llm_usage_provider_model_created",
             "idx_fact_llm_generation_provider_model_created"),
        ),
    ),
    (
        "llm_usage_daily_rollup",
        "agg_llm_usage_daily",
        (
            ("uq_llm_usage_daily_rollup_scope",
             "uq_agg_llm_usage_daily_scope"),
            ("idx_llm_usage_daily_rollup_tenant_day",
             "idx_agg_llm_usage_daily_tenant_day"),
            ("idx_llm_usage_daily_rollup_tenant_app_day",
             "idx_agg_llm_usage_daily_tenant_app_day"),
        ),
    ),
    (
        "model_pricing",
        "ref_llm_model_pricing",
        (
            ("uq_model_pricing_effective",
             "uq_ref_llm_model_pricing_effective"),
            ("idx_model_pricing_lookup",
             "idx_ref_llm_model_pricing_lookup"),
            ("idx_model_pricing_source_snapshot",
             "idx_ref_llm_model_pricing_source_snapshot"),
        ),
    ),
    # model_aliases: constraint/index names use the singular ``model_alias``
    # logical prefix (uq_model_alias_scope, idx_model_alias_lookup) rather
    # than the plural physical table name, so they don't embed the old
    # name and aren't renamed here.
    ("model_aliases", "ref_llm_model_alias", ()),
    (
        "models_dev_catalog",
        "ref_llm_models_catalog",
        (
            ("uq_models_dev_catalog_provider_model",
             "uq_ref_llm_models_catalog_provider_model"),
            ("idx_models_dev_catalog_source_id",
             "idx_ref_llm_models_catalog_source_id"),
            ("idx_models_dev_catalog_status",
             "idx_ref_llm_models_catalog_status"),
        ),
    ),
    (
        "models_dev_snapshots",
        "snapshot_llm_models_catalog",
        (
            ("idx_models_dev_snapshots_fetched_at",
             "idx_snapshot_llm_models_catalog_fetched_at"),
            ("idx_models_dev_snapshots_payload_hash",
             "idx_snapshot_llm_models_catalog_payload_hash"),
        ),
    ),
)


def upgrade() -> None:
    assert len(_TABLE_RENAMES) == 15, (
        f"expected 15 table renames per plan §5.10–§5.13, got {len(_TABLE_RENAMES)}"
    )
    for old_table, new_table, refactors in _TABLE_RENAMES:
        for old_name, new_name in refactors:
            # ``ALTER INDEX`` works for both indexes and unique-index-backed
            # constraints. ``ALTER TABLE ... RENAME CONSTRAINT`` is required
            # for FK constraints. Use the unified form here: postgres looks
            # up the object by name in the table's schema.
            if old_name.startswith("fk_"):
                op.execute(
                    f"ALTER TABLE analytics.{old_table} "
                    f"RENAME CONSTRAINT {old_name} TO {new_name}"
                )
            else:
                op.execute(
                    f"ALTER INDEX analytics.{old_name} RENAME TO {new_name}"
                )
        op.execute(f"ALTER TABLE analytics.{old_table} RENAME TO {new_table}")


def downgrade() -> None:
    # Reverse order: rename the table back first, then the indexes /
    # constraints. ``ALTER INDEX`` references the index by its current
    # (new) name in the (still-renamed) table's schema, then the table
    # rename restores the prior name.
    for old_table, new_table, refactors in reversed(_TABLE_RENAMES):
        op.execute(f"ALTER TABLE analytics.{new_table} RENAME TO {old_table}")
        for old_name, new_name in reversed(refactors):
            if old_name.startswith("fk_"):
                op.execute(
                    f"ALTER TABLE analytics.{old_table} "
                    f"RENAME CONSTRAINT {new_name} TO {old_name}"
                )
            else:
                op.execute(
                    f"ALTER INDEX analytics.{new_name} RENAME TO {old_name}"
                )
