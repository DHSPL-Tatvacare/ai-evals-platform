"""catch-up indexes and defaults (bucket B from Phase 0)

Brings prod up to parity with `Base.metadata` for two model-only items
that never made it via startup_schema.py:

- B1: missing btree index `ix_report_configs_source_session_id`.
- B2: `sherlock_runtime_sessions.scratchpad` default — drop the legacy
  `composed_report` key per the deliberate model default. Existing rows
  are unaffected; only new inserts use the new default. App code on
  load tolerates rows that still carry the legacy key.

Idempotent on prod and fresh dev DBs alike. Safe to run after any state.

Revision ID: 0002_catchup_indexes_defaults
Revises: 0001_baseline_prod
Create Date: 2026-04-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0002_catchup_indexes_defaults"
down_revision: Union[str, None] = "0001_baseline_prod"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Match the SQLAlchemy server_default text on
# backend/app/models/sherlock_runtime.py:31-33 exactly so future
# `alembic revision --autogenerate` does not see drift on this column.
_SCRATCHPAD_DEFAULT_NEW = (
    '{"findings": [], "errors": [], "discovery": null, "lookups": {}, '
    '"resolved_entities": {}, "active_filters": {}, '
    '"discovered_schema": {"tables_inspected": [], "columns_by_table": {}, '
    '"relations_found": [], "json_structures": {}}, '
    '"last_analysis": null, "analysis_history": [], '
    '"last_evidence": null, "last_data_check": null}'
)

# What prod currently has (from prod_schema_snapshot.sql) — used for downgrade.
_SCRATCHPAD_DEFAULT_LEGACY = (
    '{"errors": [], "lookups": {}, "findings": [], "discovery": null, '
    '"last_analysis": null, "last_evidence": null, "active_filters": {}, '
    '"composed_report": null, "last_data_check": null, '
    '"analysis_history": [], '
    '"discovered_schema": {"json_structures": {}, "relations_found": [], '
    '"columns_by_table": {}, "tables_inspected": []}, '
    '"resolved_entities": {}}'
)


def upgrade() -> None:
    # B1 — missing btree index on report_configs.source_session_id.
    # `IF NOT EXISTS` guards against any prior hand-creation; alembic itself
    # will only attempt this once because the migration is recorded.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_report_configs_source_session_id "
        "ON report_configs (source_session_id)"
    )

    # B2 — align scratchpad default with the deliberate model shape.
    op.execute(
        f"ALTER TABLE sherlock_runtime_sessions "
        f"ALTER COLUMN scratchpad "
        f"SET DEFAULT '{_SCRATCHPAD_DEFAULT_NEW}'::jsonb"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE sherlock_runtime_sessions "
        f"ALTER COLUMN scratchpad "
        f"SET DEFAULT '{_SCRATCHPAD_DEFAULT_LEGACY}'::jsonb"
    )
    op.execute("DROP INDEX IF EXISTS ix_report_configs_source_session_id")
