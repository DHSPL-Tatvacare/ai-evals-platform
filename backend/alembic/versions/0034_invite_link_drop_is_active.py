"""invite link lifecycle — drop legacy is_active column

Revision ID: 0034_invite_link_drop_is_active
Revises: 0033_invite_link_lifecycle_additive
Create Date: 2026-05-08

Phase 4 of the invite-link lifecycle rebuild
(docs/plans/2026-05-08-invite-link-lifecycle/phase-04-subtractive.md).

Pre-flight gate (must be verified before applying):
1. Phase 3 has been in production for at least one release.
2. Container logs show zero hits to the legacy
   ``DELETE /api/admin/invite-links/{id}`` soft-revoke route over the
   past 14 days (Phase 2 logged a ``warn`` per hit).
3. No external scripts or integrations call the old shape.

Subtractive only: drops ``is_active``. The ``status`` enum column
(added in Phase 1) is the sole source of truth from here on.

Downgrade is best-effort and lossy: the original boolean's history
is reconstructed from the enum (``is_active = (status = 'active')``).
A row that was revoked ``is_active=False`` and a row that was expired
``is_active=False`` both backfill identically because the original
distinction lived only in the legacy column. Downgrade should never
be needed in prod.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0034_invite_link_drop_is_active"
down_revision: Union[str, None] = "0033_invite_link_lifecycle_additive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE platform.identity_invite_links DROP COLUMN is_active"
    )


def downgrade() -> None:
    # Re-add the column nullable + defaulted, backfill from ``status``,
    # then enforce NOT NULL. Doing it in this order keeps the migration
    # online-safe on a populated table.
    op.execute(
        "ALTER TABLE platform.identity_invite_links "
        "ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        """
        UPDATE platform.identity_invite_links
        SET is_active = (status = 'active')
        """
    )
