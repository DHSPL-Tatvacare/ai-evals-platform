"""evaluation TXN spine — platform.evaluation_targets / evaluations / evaluation_details.

Additive: introduces the unified Run → Target → Evaluation → Detail write path.
No data move; old result/summary/thread_results stay until Phase 4.

Revision ID: 0088
Revises: 0087
Create Date: 2026-06-03
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0088"
down_revision: Union[str, None] = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=50), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["platform.evaluation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "target_key", name="uq_evaluation_targets_run_target"),
        schema="platform",
    )
    op.create_index("ix_evaluation_targets_run_id", "evaluation_targets", ["run_id"], schema="platform")
    op.create_index("idx_evaluation_targets_tenant_app", "evaluation_targets", ["tenant_id", "app_id"], schema="platform")

    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=50), nullable=False),
        sa.Column("evaluator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluator_ref", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("headline_key", sa.Text(), nullable=True),
        sa.Column("headline_score", sa.Numeric(), nullable=True),
        sa.Column("headline_max", sa.Numeric(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["platform.evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["platform.evaluation_targets.id"], ondelete="CASCADE"),
        schema="platform",
    )
    op.create_index("ix_evaluations_run_id", "evaluations", ["run_id"], schema="platform")
    op.create_index("ix_evaluations_target_id", "evaluations", ["target_id"], schema="platform")
    op.create_index("idx_evaluations_evaluator", "evaluations", ["evaluator_id"], schema="platform")

    op.create_table(
        "evaluation_details",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True, nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=50), nullable=False),
        sa.Column("style", sa.String(length=16), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("max", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("weight", sa.Numeric(), nullable=True),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("candidate_text", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["evaluation_id"], ["platform.evaluations.id"], ondelete="CASCADE"),
        schema="platform",
    )
    op.create_index("ix_evaluation_details_evaluation_id", "evaluation_details", ["evaluation_id"], schema="platform")
    op.create_index("idx_evaluation_details_run_style_key", "evaluation_details",
                    ["run_id", "style", "key"], schema="platform")
    op.create_index("idx_evaluation_details_tenant_app_style_key", "evaluation_details",
                    ["tenant_id", "app_id", "style", "key"], schema="platform")


def downgrade() -> None:
    op.drop_table("evaluation_details", schema="platform")
    op.drop_table("evaluations", schema="platform")
    op.drop_table("evaluation_targets", schema="platform")
