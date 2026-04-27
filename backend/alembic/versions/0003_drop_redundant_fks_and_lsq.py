"""drop redundant duplicate FKs and dead lsq_lead_cache table (bucket D)

- D1: `lsq_lead_cache` table — model removed in commit 50baf9f. Already
  dropped from prod by `startup_schema.py:123` ("DROP TABLE IF EXISTS
  lsq_lead_cache") on a recent deploy, so on prod this is a no-op. Fresh
  dev DBs that came through the baseline still have it; the migration
  drops it there.

- D2 / D3: `fk_analytics_charts_source_session_id` and
  `fk_analytics_dashboards_source_session_id` are duplicate FKs on the
  same column with the same delete behaviour as the SQLAlchemy-default
  `*_source_session_id_fkey` already on each table. The duplicate names
  were added by old `startup_schema.py` DO blocks (which are removed in
  the same commit as this migration to prevent re-creation on subsequent
  boots). The remaining `*_fkey` FKs continue to enforce referential
  integrity.

Revision ID: 0003_drop_redundant_fks_and_lsq
Revises: 0002_catchup_indexes_defaults
Create Date: 2026-04-27
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0003_drop_redundant_fks_and_lsq"
down_revision: Union[str, None] = "0002_catchup_indexes_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # D2 + D3 — drop duplicate FKs. IF EXISTS for safety in case prod or
    # a dev DB has already removed them by other means.
    op.execute(
        "ALTER TABLE analytics_charts "
        "DROP CONSTRAINT IF EXISTS fk_analytics_charts_source_session_id"
    )
    op.execute(
        "ALTER TABLE analytics_dashboards "
        "DROP CONSTRAINT IF EXISTS fk_analytics_dashboards_source_session_id"
    )

    # D1 — drop dead lsq_lead_cache table. IF EXISTS because prod already
    # dropped it via startup_schema.py during a Phase 0 deploy.
    op.execute("DROP TABLE IF EXISTS lsq_lead_cache")


def downgrade() -> None:
    # Recreate empty lsq_lead_cache for rollback parity. Data is unrecoverable.
    op.execute("""
        CREATE TABLE IF NOT EXISTS lsq_lead_cache (
            id uuid NOT NULL,
            prospect_id varchar(100) NOT NULL,
            first_name varchar(255),
            last_name varchar(255),
            phone varchar(50),
            email varchar(255),
            fetched_at timestamptz NOT NULL DEFAULT now(),
            tenant_id uuid NOT NULL,
            user_id uuid NOT NULL,
            CONSTRAINT lsq_lead_cache_pkey PRIMARY KEY (id),
            CONSTRAINT uq_lsq_lead_cache_tenant_prospect UNIQUE (tenant_id, prospect_id),
            CONSTRAINT lsq_lead_cache_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
            CONSTRAINT lsq_lead_cache_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lsq_lead_cache_tenant "
        "ON lsq_lead_cache (tenant_id)"
    )
    op.execute(
        "ALTER TABLE analytics_dashboards "
        "ADD CONSTRAINT fk_analytics_dashboards_source_session_id "
        "FOREIGN KEY (source_session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE analytics_charts "
        "ADD CONSTRAINT fk_analytics_charts_source_session_id "
        "FOREIGN KEY (source_session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL"
    )
