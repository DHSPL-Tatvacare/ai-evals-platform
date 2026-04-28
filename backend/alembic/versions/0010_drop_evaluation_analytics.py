"""drop legacy analytics.evaluation_analytics cache table

Roadmap 01 §3.3 + §9.3 revision 0010. The ``evaluation_analytics``
table was a single-row + cross-run cache for the legacy report path
(``routes/reports.py`` cross-run handlers + ``services/reports/
base_report_service.py``). The new pipeline (``report_builder_v2`` /
``report_generation_service``) does not consume it, and the analytics
fact tables (``analytics.fact_evaluation`` /
``analytics.fact_evaluation_criterion`` / ``analytics.agg_evaluation_run``)
fully shadow its purpose.

This commit removes the in-process readers (route handlers + base
report service cache helpers + ORM model + tests) alongside the
migration, so the table has no live consumer at upgrade time.

Reversibility: downgrade re-creates the table with its original column
shape, FKs, and indexes inline. The downgrade does not depend on the
deleted ORM model file — every column definition is replayed
verbatim.

Revision ID: 0010_drop_evaluation_analytics
Revises: 0009_rename_analytics_tables_role_prefixed
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0010_drop_evaluation_analytics"
down_revision: Union[str, None] = "0009_rename_analytics_tables_role_prefixed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "idx_analytics_tenant_app",
        table_name="evaluation_analytics",
        schema="analytics",
    )
    op.drop_index(
        "idx_analytics_app_scope",
        table_name="evaluation_analytics",
        schema="analytics",
    )
    op.drop_index(
        "uq_analytics_cross_run_per_app",
        table_name="evaluation_analytics",
        schema="analytics",
    )
    op.drop_table("evaluation_analytics", schema="analytics")


def downgrade() -> None:
    op.create_table(
        "evaluation_analytics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("app_id", sa.String(length=50), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.eval_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("analytics_data", postgresql.JSONB, nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("source_run_count", sa.Integer, nullable=True),
        sa.Column(
            "latest_source_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "scope", "run_id",
            name="uq_analytics_app_scope_run",
        ),
        schema="analytics",
    )
    op.create_index(
        "uq_analytics_cross_run_per_app",
        "evaluation_analytics",
        ["tenant_id", "app_id"],
        unique=True,
        postgresql_where=sa.text("scope = 'cross_run'"),
        schema="analytics",
    )
    op.create_index(
        "idx_analytics_app_scope",
        "evaluation_analytics",
        ["app_id", "scope"],
        schema="analytics",
    )
    op.create_index(
        "idx_analytics_tenant_app",
        "evaluation_analytics",
        ["tenant_id", "app_id"],
        schema="analytics",
    )
