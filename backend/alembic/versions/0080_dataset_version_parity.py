"""orchestration: dataset version-parity additive columns

Revision ID: 0080
Revises: 0079
Create Date: 2026-05-25

Additive parity columns on cohort_datasets / cohort_dataset_versions to match
the workflow + cohort-definition publish lifecycle. communication_key lands as
NOT NULL DEFAULT '' so existing inserts that omit it keep working; a later
phase enforces a real value at upload. version_number is intentionally NOT
renamed.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0080"
down_revision: Union[str, None] = "0079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orchestration.cohort_datasets "
        "ADD COLUMN active BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_datasets "
        "ADD COLUMN current_published_version_id UUID"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions "
        "ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'draft'"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions "
        "ADD CONSTRAINT ck_cohort_dataset_versions_status "
        "CHECK (status IN ('draft','published','archived'))"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions "
        "ADD COLUMN communication_key VARCHAR(200) NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions "
        "ADD COLUMN published_by UUID REFERENCES platform.users(id)"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions "
        "ADD COLUMN published_at TIMESTAMPTZ"
    )

    # Deferred so a publish flow can flip the version status and the parent
    # current_published_version_id in one transaction without ordering the UPDATEs.
    op.execute(
        """
        ALTER TABLE orchestration.cohort_datasets
        ADD CONSTRAINT fk_cohort_datasets_current_published_version
        FOREIGN KEY (current_published_version_id)
        REFERENCES orchestration.cohort_dataset_versions(id)
        DEFERRABLE INITIALLY DEFERRED
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE orchestration.cohort_datasets "
        "DROP CONSTRAINT IF EXISTS fk_cohort_datasets_current_published_version"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions "
        "DROP CONSTRAINT IF EXISTS ck_cohort_dataset_versions_status"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions DROP COLUMN IF EXISTS published_at"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions DROP COLUMN IF EXISTS published_by"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions DROP COLUMN IF EXISTS communication_key"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_dataset_versions DROP COLUMN IF EXISTS status"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_datasets DROP COLUMN IF EXISTS current_published_version_id"
    )
    op.execute(
        "ALTER TABLE orchestration.cohort_datasets DROP COLUMN IF EXISTS active"
    )
