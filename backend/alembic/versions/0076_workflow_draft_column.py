"""add workflows.draft_definition + archive orphan draft versions

Revision ID: 0076
Revises: 0075
Create Date: 2026-05-23

A workflow now carries one mutable draft inline on the workflows row; published
versions stay immutable history. This adds draft_definition + draft_updated_at,
seeds each workflow's draft from its live (or highest) version, and archives the
orphan status='draft' rows that the old save-mints-a-version model accumulated.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0076"
down_revision: Union[str, None] = "0075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE orchestration.workflows
            ADD COLUMN IF NOT EXISTS draft_definition JSONB,
            ADD COLUMN IF NOT EXISTS draft_updated_at TIMESTAMPTZ
        """
    )

    op.execute(
        """
        UPDATE orchestration.workflows w
        SET draft_definition = v.definition,
            draft_updated_at = now()
        FROM orchestration.workflow_versions v
        WHERE w.current_published_version_id = v.id
          AND w.current_published_version_id IS NOT NULL
        """
    )

    # Draft-only workflows seed from their highest-version row.
    op.execute(
        """
        UPDATE orchestration.workflows w
        SET draft_definition = v.definition,
            draft_updated_at = now()
        FROM (
            SELECT DISTINCT ON (workflow_id) workflow_id, definition
            FROM orchestration.workflow_versions
            ORDER BY workflow_id, version DESC
        ) v
        WHERE w.current_published_version_id IS NULL
          AND v.workflow_id = w.id
        """
    )

    op.execute(
        """
        UPDATE orchestration.workflow_versions
        SET status = 'archived'
        WHERE status = 'draft'
        """
    )


def downgrade() -> None:
    # Archived drafts are terminal; we only drop the new columns.
    op.execute(
        """
        ALTER TABLE orchestration.workflows
            DROP COLUMN IF EXISTS draft_definition,
            DROP COLUMN IF EXISTS draft_updated_at
        """
    )
