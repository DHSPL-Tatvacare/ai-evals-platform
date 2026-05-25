"""rewrite access_role_permissions to the four-verb permission vocabulary

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-25

Standardizes permission ids to {view, manage, run, export} and folds redundant
verbs into their owning capability. Rewrites every tenant role's
``platform.access_role_permissions.permission`` old->new. Merges (e.g. the four
``asset:*`` verbs -> ``asset:manage``) collapse via DELETE of duplicates after
the UPDATE. The Owner role bypasses permission checks and has no rows here.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0079"
down_revision: Union[str, None] = "0078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# old permission id -> new permission id (the full rename + merge set).
_OLD_TO_NEW: dict[str, str] = {
    "listing:create": "listing:manage",
    "listing:delete": "listing:manage",
    "evaluation:cancel": "evaluation:run",
    "evaluation:delete": "evaluation:manage",
    "asset:create": "asset:manage",
    "asset:edit": "asset:manage",
    "asset:delete": "asset:manage",
    "asset:share": "asset:manage",
    "orchestration:admin:comm_cap": "orchestration:manage",
    "report:generate": "report:run",
    "configuration:edit": "configuration:manage",
    "cost:edit": "cost:manage",
    "analytics:admin": "analytics:manage",
    "sherlock:manage_verified_queries": "sherlock:manage",
    "user:create": "user:manage",
    "user:edit": "user:manage",
    "user:deactivate": "user:manage",
    "user:delete": "user:manage",
    "user:reset_password": "user:manage",
    "role:assign": "role:manage",
    "invite_link:delete": "invite_link:manage",
    "platform:edit": "platform:manage",
}

# Best-effort reverse: each merged target maps back to ONE representative old id.
# Lossy by construction (many old verbs collapsed into one). Old ids that were
# already canonical (evaluation:run, orchestration:manage, ...) are untouched in
# both directions.
_NEW_TO_OLD: dict[str, str] = {
    "listing:manage": "listing:create",
    "evaluation:manage": "evaluation:delete",
    "asset:manage": "asset:create",
    "report:run": "report:generate",
    "configuration:manage": "configuration:edit",
    "cost:manage": "cost:edit",
    "analytics:manage": "analytics:admin",
    "sherlock:manage": "sherlock:manage_verified_queries",
    "user:manage": "user:create",
    "role:manage": "role:assign",
    "invite_link:manage": "invite_link:manage",
    "platform:manage": "platform:edit",
}


_DELETE_DUPES = sa.text(
    """
    DELETE FROM platform.access_role_permissions arp
    WHERE arp.permission = :old
      AND EXISTS (
          SELECT 1 FROM platform.access_role_permissions other
          WHERE other.role_id = arp.role_id
            AND other.permission = :new
      )
    """
)
_RENAME = sa.text(
    """
    UPDATE platform.access_role_permissions
    SET permission = :new
    WHERE permission = :old
    """
)


def _remap(mapping: dict[str, str]) -> None:
    bind = op.get_bind()
    for old, new in mapping.items():
        if old == new:
            continue
        # Drop rows whose role already holds the target permission (would clash
        # with uq_access_role_permission once renamed), then rename the rest.
        bind.execute(_DELETE_DUPES, {"old": old, "new": new})
        bind.execute(_RENAME, {"old": old, "new": new})


def upgrade() -> None:
    _remap(_OLD_TO_NEW)


def downgrade() -> None:
    _remap(_NEW_TO_OLD)
