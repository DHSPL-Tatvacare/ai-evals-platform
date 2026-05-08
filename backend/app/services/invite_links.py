"""Service-layer helpers for the invite-link lifecycle.

Phase 1 surface: ``compute_invite_status`` (pure state-machine function)
and ``hash_ip`` (privacy-safe IP correlation for the redemption audit
table).

Phase 2 surface: state-mutating service functions — ``revoke_invite_link``,
``hard_delete_invite_link``, ``list_invite_uses``,
``lazily_persist_status_corrections``. The route layer becomes a thin
HTTP error mapping over these.

The pure helpers (``compute_invite_status``, ``hash_ip``) have no DB
imports so the model can call back into them without circular-import
risk; the DB-bound functions live below the dividing comment.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite_link import IdentityInviteLink, InviteStatus
from app.models.invite_link_use import IdentityInviteLinkUse
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)


class InviteLinkAlreadyTerminal(Exception):
    """Raised when a state transition is attempted on a non-active invite.

    The argument is the current status value (e.g. ``"revoked"``). Routes
    map this to ``HTTPException(409, …)``.
    """


class InviteLinkNotTerminal(Exception):
    """Raised when hard-delete is attempted on an active invite. Hard-delete
    is reserved for terminal rows so the audit story stays clean: revoke
    first, then delete."""


# ── Pure helpers (no DB) ─────────────────────────────────────────────────────


def compute_invite_status(
    *,
    is_revoked: bool,
    expires_at: datetime,
    max_uses: Optional[int],
    uses_count: int,
    now: datetime,
) -> InviteStatus:
    """Derive the canonical status for an invite link.

    Mirrors design-spec §7.1. Order matters: revoked beats expired beats
    exhausted. ``is_revoked`` is sourced from ``revoked_at IS NOT NULL`` on
    the row — never from a separate boolean knob.
    """
    if is_revoked:
        return InviteStatus.revoked
    if expires_at <= now:
        return InviteStatus.expired
    if max_uses is not None and uses_count >= max_uses:
        return InviteStatus.exhausted
    return InviteStatus.active


def refresh_invite_status(
    invite: IdentityInviteLink,
    *,
    now: Optional[datetime] = None,
) -> InviteStatus:
    """Recompute and persist the current row-local lifecycle status.

    This is the write-path companion to the list route's lazy correction:
    any code path that gates behavior on "is this invite still active?"
    must first normalize stale ``status='active'`` rows whose timer ran out
    or whose ``max_uses`` has been hit.
    """
    current_now = now or datetime.now(timezone.utc)
    derived = compute_invite_status(
        is_revoked=invite.is_revoked,
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
        uses_count=invite.uses_count,
        now=current_now,
    )
    if invite.status != derived:
        invite.status = derived
    return invite.status


def hash_ip(ip: Optional[str], tenant_id: uuid.UUID) -> Optional[str]:
    """Per-tenant salted SHA-256 of a client IP. Returns 64-char hex.

    ``None`` in → ``None`` out (e.g. test clients without a peer address).
    Salt is the tenant's UUID bytes — stable, tenant-scoped, never leaks
    across tenants.
    """
    if not ip:
        return None
    digest = hashlib.sha256()
    digest.update(tenant_id.bytes)
    digest.update(ip.encode("utf-8"))
    return digest.hexdigest()


# ── DB-bound services ────────────────────────────────────────────────────────


# Lazy correction is bounded so a list query never amplifies into a large
# write fan-out. Anything beyond this falls to a future sweeper job.
_LAZY_CORRECTION_CAP = 50


async def revoke_invite_link(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    invite_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_email: str,
    request: Optional[Request] = None,
) -> IdentityInviteLink:
    """Revoke an invite link inside a ``FOR UPDATE`` window.

    Raises ``LookupError`` (route → 404) or ``InviteLinkAlreadyTerminal``
    (route → 409). Writes the audit log entry inside the same
    transaction so route handlers don't have to remember to call it.
    Caller is responsible for ``db.commit()``.
    """
    invite = await db.scalar(
        select(IdentityInviteLink)
        .where(
            IdentityInviteLink.id == invite_id,
            IdentityInviteLink.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if not invite:
        raise LookupError("invite link not found")
    now = datetime.now(timezone.utc)
    current_status = refresh_invite_status(invite, now=now)
    if current_status != InviteStatus.active:
        raise InviteLinkAlreadyTerminal(current_status.value)

    invite.status = InviteStatus.revoked
    invite.revoked_at = now
    invite.revoked_by = actor_id
    invite.revoked_by_email_snapshot = actor_email

    await write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="invite_link:revoke",
        entity_type="invite_link",
        entity_id=invite.id,
        before_state={"status": InviteStatus.active.value},
        after_state={
            "status": InviteStatus.revoked.value,
            "revoked_at": now.isoformat(),
            "revoked_by": str(actor_id),
        },
        request=request,
    )
    return invite


async def hard_delete_invite_link(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    invite_id: uuid.UUID,
    actor_id: uuid.UUID,
    request: Optional[Request] = None,
) -> None:
    """Permanently delete a terminal invite. ``_uses`` rows cascade.

    Raises ``LookupError`` (route → 404) or ``InviteLinkNotTerminal``
    (route → 409). Audited as ``invite_link:delete``. Caller commits.
    """
    invite = await db.scalar(
        select(IdentityInviteLink)
        .where(
            IdentityInviteLink.id == invite_id,
            IdentityInviteLink.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if not invite:
        raise LookupError("invite link not found")
    current_status = refresh_invite_status(invite)
    if current_status == InviteStatus.active:
        raise InviteLinkNotTerminal(current_status.value)

    snapshot = {
        "label": invite.label,
        "status": invite.status.value,
        "uses_count": invite.uses_count,
        "max_uses": invite.max_uses,
    }
    await write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="invite_link:delete",
        entity_type="invite_link",
        entity_id=invite.id,
        before_state=snapshot,
        after_state=None,
        request=request,
    )
    await db.delete(invite)


async def list_invite_uses(
    db: AsyncSession,
    *,
    invite_link_id: uuid.UUID,
) -> Sequence[IdentityInviteLinkUse]:
    """Redemptions for a single invite, newest first."""
    result = await db.execute(
        select(IdentityInviteLinkUse)
        .where(IdentityInviteLinkUse.invite_link_id == invite_link_id)
        .order_by(IdentityInviteLinkUse.used_at.desc())
    )
    return result.scalars().all()


async def lazily_persist_status_corrections(
    invites: Iterable[IdentityInviteLink],
) -> list[IdentityInviteLink]:
    """For each invite still labelled ``active`` whose timer ran out or
    whose ``max_uses`` was hit, persist the corrected status.

    Mutates session-bound ``IdentityInviteLink`` instances in place;
    SQLAlchemy flushes the changes on the caller's commit.

    Idempotent. Bounded at ``_LAZY_CORRECTION_CAP`` writes per call so a
    list query can never amplify into a large fan-out — the rest fall to
    a future sweeper job. Returns the input list with corrected
    ``status`` attributes so callers can render immediately. Caller is
    responsible for ``db.commit()``.
    """
    invites = list(invites)
    now = datetime.now(timezone.utc)
    corrections_applied = 0
    for invite in invites:
        if corrections_applied >= _LAZY_CORRECTION_CAP:
            break
        if invite.status != InviteStatus.active:
            continue
        derived = refresh_invite_status(invite, now=now)
        if derived == InviteStatus.active:
            continue
        # Only ``expired`` or ``exhausted`` reach here — ``revoked`` is
        # never set passively and is gated by the CHECK constraint
        # against a NULL ``revoked_at``.
        corrections_applied += 1

    if corrections_applied > 0:
        logger.info(
            "lazy invite-link status correction applied to %d row(s)",
            corrections_applied,
        )
    return invites
