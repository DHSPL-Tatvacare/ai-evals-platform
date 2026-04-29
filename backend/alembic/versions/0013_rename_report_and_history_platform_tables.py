"""rename 4 report+history platform tables to their final names

Roadmap 01 §5.11 revision 0013. Reports + history rename **within
``platform``** (no schema move). Four tables get their final names.

Renames (4):
  report_configs    -> report_configurations
  report_runs       -> report_generation_runs
  report_artifacts  -> report_generated_artifacts
  history           -> application_event_history

Indexes and unique-constraint names that explicitly embed the old
physical table name are renamed in lockstep so the live catalog stays
consistent with the ORM ``__table_args__`` declarations.

Three SQLAlchemy ``index=True`` auto-named indexes are also renamed
into the schema-qualified ``ix_<schema>_<table>_<column>`` shape that
SQLAlchemy expects under ``include_schemas=True`` (Roadmap 01 §9.5):

  ix_report_configs_app_id            -> ix_platform_report_configurations_app_id
  ix_report_configs_source_session_id -> ix_platform_report_configurations_source_session_id
  ix_report_runs_app_id               -> ix_platform_report_generation_runs_app_id

These three were created by the prod baseline (``ix_report_configs_app_id``,
``ix_report_runs_app_id``) and revision 0002 catch-up
(``ix_report_configs_source_session_id``); the ORM declares them via
``index=True`` on ``ReportConfiguration.app_id``,
``ReportConfiguration.source_session_id``, and
``ReportGenerationRun.app_id``. Without renaming them here, the live
catalog drifts from ``Base.metadata`` after 0013 applies.

Postgres-auto-generated names (``*_pkey``, ``*_fkey``,
``*_<col>_<col>_key``) are left as-is — same precedent as revisions
0009 / 0011 / 0012.

Reversibility: downgrade reverses every rename (table + indexes +
constraints) in symmetric order.

Revision ID: 0013_rename_report_and_history_platform_tables
Revises: 0012_rename_evaluation_platform_tables
Create Date: 2026-04-29
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0013_rename_report_and_history_platform_tables"
down_revision: Union[str, None] = "0012_rename_evaluation_platform_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (old_table, new_table, [(old_index_or_constraint, new_index_or_constraint), ...])
# Auto-generated ``*_pkey`` / ``*_fkey`` / ``*_<col>_<col>_key`` names are
# left untouched to keep the diff surface minimal — same precedent as
# revisions 0009 / 0011 / 0012.
_TABLE_RENAMES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "report_configs",
        "report_configurations",
        (
            (
                "uq_report_configs_tenant_app_report",
                "uq_report_configurations_tenant_app_report",
            ),
            (
                "idx_report_configs_tenant_app_scope",
                "idx_report_configurations_tenant_app_scope",
            ),
            (
                "idx_report_configs_tenant_app_default",
                "idx_report_configurations_tenant_app_default",
            ),
            (
                "ix_report_configs_app_id",
                "ix_platform_report_configurations_app_id",
            ),
            (
                "ix_report_configs_source_session_id",
                "ix_platform_report_configurations_source_session_id",
            ),
        ),
    ),
    (
        "report_runs",
        "report_generation_runs",
        (
            (
                "idx_report_runs_tenant_app_report",
                "idx_report_generation_runs_tenant_app_report",
            ),
            (
                "idx_report_runs_tenant_app_scope",
                "idx_report_generation_runs_tenant_app_scope",
            ),
            (
                "idx_report_runs_tenant_status_created",
                "idx_report_generation_runs_tenant_status_created",
            ),
            (
                "idx_report_runs_job_id",
                "idx_report_generation_runs_job_id",
            ),
            (
                "ix_report_runs_app_id",
                "ix_platform_report_generation_runs_app_id",
            ),
        ),
    ),
    (
        "report_artifacts",
        "report_generated_artifacts",
        (
            (
                "uq_report_artifacts_report_run",
                "uq_report_generated_artifacts_report_run",
            ),
            (
                "idx_report_artifacts_tenant_app_scope",
                "idx_report_generated_artifacts_tenant_app_scope",
            ),
            (
                "idx_report_artifacts_content_hash",
                "idx_report_generated_artifacts_content_hash",
            ),
        ),
    ),
    (
        "history",
        "application_event_history",
        (
            ("idx_history_timestamp", "idx_application_event_history_timestamp"),
            ("idx_history_entity", "idx_application_event_history_entity"),
            ("idx_history_source", "idx_application_event_history_source"),
            (
                "idx_history_app_source",
                "idx_application_event_history_app_source",
            ),
            (
                "idx_history_entity_source",
                "idx_application_event_history_entity_source",
            ),
            ("idx_history_tenant", "idx_application_event_history_tenant"),
            (
                "idx_history_tenant_user",
                "idx_application_event_history_tenant_user",
            ),
        ),
    ),
)


def upgrade() -> None:
    assert len(_TABLE_RENAMES) == 4, (
        f"expected 4 table renames per plan §5.11, got {len(_TABLE_RENAMES)}"
    )
    for old_table, new_table, refactors in _TABLE_RENAMES:
        for old_name, new_name in refactors:
            op.execute(
                f"ALTER INDEX platform.{old_name} RENAME TO {new_name}"
            )
        op.execute(
            f"ALTER TABLE platform.{old_table} RENAME TO {new_table}"
        )


def downgrade() -> None:
    # Reverse: rename the table back first, then the indexes / constraints.
    for old_table, new_table, refactors in reversed(_TABLE_RENAMES):
        op.execute(
            f"ALTER TABLE platform.{new_table} RENAME TO {old_table}"
        )
        for old_name, new_name in reversed(refactors):
            op.execute(
                f"ALTER INDEX platform.{new_name} RENAME TO {old_name}"
            )
