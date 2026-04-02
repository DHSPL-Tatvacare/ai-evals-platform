"""Admin API routes — database stats, selective data erasure, user management, tenant management, invite links."""
import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context, require_owner
from app.auth.permissions import require_permission
from app.auth.utils import create_refresh_token, hash_password, hash_refresh_token
from app.database import get_db
from app.models.invite_link import InviteLink
from app.models.listing import Listing
from app.models.eval_run import EvalRun, ThreadEvaluation, AdversarialEvaluation, ApiLog
from app.models.chat import ChatSession, ChatMessage
from app.models.file_record import FileRecord
from app.models.prompt import Prompt
from app.models.schema import Schema
from app.models.evaluator import Evaluator
from app.models.job import Job
from app.models.history import History
from app.models.setting import Setting
from app.models.mixins.shareable import Visibility
from app.models.tag import Tag
from app.models.user import User, RefreshToken
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.schemas.base import CamelModel
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ── Request schemas ───────────────────────────────────────────────────────────


class EraseRequest(CamelModel):
    app_id: Optional[str] = None
    targets: list[str] = []
    include_seed_data: bool = False


class CreateUserRequest(CamelModel):
    email: str
    password: str
    display_name: str
    role_id: str


class UpdateUserRequest(CamelModel):
    display_name: Optional[str] = None
    role_id: Optional[str] = None
    is_active: Optional[bool] = None


class UpdateTenantRequest(CamelModel):
    name: Optional[str] = None


# ── GET /api/admin/stats ──────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    app_id: Optional[str] = None,
    auth: AuthContext = require_permission('analytics:view'),
    db: AsyncSession = Depends(get_db),
):
    """Return per-table record counts within tenant. Optionally filtered by app_id."""
    tables: dict = {}

    # Helper: count rows with tenant filter + optional app_id
    async def count_table(model, app_col=None):
        q = select(func.count()).select_from(model)
        if hasattr(model, "tenant_id"):
            q = q.where(model.tenant_id == auth.tenant_id)
        if app_id and app_col is not None:
            q = q.where(app_col == app_id)
        result = await db.execute(q)
        return result.scalar() or 0

    # Helper: count by app_id grouping within tenant
    async def count_by_app(model, app_col):
        q = select(app_col, func.count()).select_from(model).group_by(app_col)
        if hasattr(model, "tenant_id"):
            q = q.where(model.tenant_id == auth.tenant_id)
        result = await db.execute(q)
        return {row[0]: row[1] for row in result}

    # Helper: seed/user breakdown for seeded tables
    async def count_with_seed(model, app_col, is_seed_filter, app_filter=None):
        base = select(func.count()).select_from(model)
        if hasattr(model, "tenant_id"):
            base = base.where(model.tenant_id == auth.tenant_id)
        if app_filter is not None:
            base = base.where(app_col == app_filter)

        total = (await db.execute(base)).scalar() or 0
        seed = (await db.execute(base.where(is_seed_filter))).scalar() or 0
        return {"total": total, "seed": seed, "user": total - seed}

    # ── Tables with app_id column ──
    for name, model, col in [
        ("listings", Listing, Listing.app_id),
        ("eval_runs", EvalRun, EvalRun.app_id),
        ("chat_sessions", ChatSession, ChatSession.app_id),
        ("history", History, History.app_id),
        ("tags", Tag, Tag.app_id),
    ]:
        total = await count_table(model, col)
        entry: dict = {"total": total}
        if not app_id:
            entry["byApp"] = await count_by_app(model, col)
        tables[name] = entry

    # ── Cascade children (no app_id, count via parent join) ──
    for name, model in [
        ("thread_evaluations", ThreadEvaluation),
        ("adversarial_evaluations", AdversarialEvaluation),
        ("api_logs", ApiLog),
        ("chat_messages", ChatMessage),
    ]:
        if app_id:
            # Join through parent to filter by app
            if model == ChatMessage:
                q = (select(func.count()).select_from(model)
                     .join(ChatSession, ChatMessage.session_id == ChatSession.id)
                     .where(ChatSession.app_id == app_id, ChatSession.tenant_id == auth.tenant_id))
            else:
                q = (select(func.count()).select_from(model)
                     .join(EvalRun, model.run_id == EvalRun.id)
                     .where(EvalRun.app_id == app_id, EvalRun.tenant_id == auth.tenant_id))
            total = (await db.execute(q)).scalar() or 0
        else:
            total = await count_table(model)
        tables[name] = {"total": total}

    # ── Seeded tables: prompts, schemas, evaluators ──
    from app.constants import SYSTEM_TENANT_ID
    if app_id:
        tables["prompts"] = await count_with_seed(
            Prompt, Prompt.app_id,
            (Prompt.is_default == True) & (Prompt.tenant_id == SYSTEM_TENANT_ID),
            app_filter=app_id,
        )
        tables["schemas"] = await count_with_seed(
            Schema, Schema.app_id,
            (Schema.is_default == True) & (Schema.tenant_id == SYSTEM_TENANT_ID),
            app_filter=app_id,
        )
        tables["evaluators"] = await count_with_seed(
            Evaluator, Evaluator.app_id,
            (Evaluator.visibility == Visibility.APP) & (Evaluator.listing_id == None),
            app_filter=app_id,
        )
    else:
        tables["prompts"] = await count_with_seed(
            Prompt, Prompt.app_id,
            (Prompt.is_default == True) & (Prompt.tenant_id == SYSTEM_TENANT_ID),
        )
        tables["schemas"] = await count_with_seed(
            Schema, Schema.app_id,
            (Schema.is_default == True) & (Schema.tenant_id == SYSTEM_TENANT_ID),
        )
        tables["evaluators"] = await count_with_seed(
            Evaluator, Evaluator.app_id,
            (Evaluator.visibility == Visibility.APP) & (Evaluator.listing_id == None),
        )

    # ── Tables without app_id ──
    tables["files"] = {"total": await count_table(FileRecord)}
    tables["jobs"] = {"total": await count_table(Job)}
    tables["settings"] = {"total": await count_table(Setting)}

    return {"tables": tables}


# ── POST /api/admin/erase ────────────────────────────────────────────────────

@router.post("/erase")
async def erase_data(
    body: EraseRequest,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Selectively erase database records within tenant. Owner only."""
    deleted: dict[str, int] = {}
    app_id = body.app_id
    targets = set(body.targets)
    erase_all = len(targets) == 0  # empty targets = erase everything

    logger.warning(
        "Admin erase requested: tenant_id=%s app_id=%s targets=%s include_seed=%s",
        auth.tenant_id, app_id, targets, body.include_seed_data,
    )

    # ── 1. eval_runs (CASCADE → thread_evaluations, adversarial_evaluations, api_logs) ──
    if erase_all or "eval_runs" in targets:
        q = delete(EvalRun).where(EvalRun.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(EvalRun.app_id == app_id)
        result = await db.execute(q)
        deleted["eval_runs"] = result.rowcount
        logger.info("Deleted %d eval_runs (cascade cleans children)", result.rowcount)

    # ── 2. listings (CASCADE → remaining linked eval_runs) ──
    if erase_all or "listings" in targets:
        q = delete(Listing).where(Listing.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(Listing.app_id == app_id)
        result = await db.execute(q)
        deleted["listings"] = result.rowcount

    # ── 3. chat_sessions (CASCADE → chat_messages + linked eval_runs) ──
    if erase_all or "chat_sessions" in targets:
        q = delete(ChatSession).where(ChatSession.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(ChatSession.app_id == app_id)
        result = await db.execute(q)
        deleted["chat_sessions"] = result.rowcount

    # ── 4. files (with blob cleanup) ──
    if erase_all or "files" in targets:
        from app.services.file_storage import file_storage

        # Fetch all file records within tenant
        file_q = select(FileRecord).where(FileRecord.tenant_id == auth.tenant_id)
        file_result = await db.execute(file_q)
        file_records = file_result.scalars().all()

        blob_errors = 0
        for rec in file_records:
            try:
                await file_storage.delete(rec.storage_path)
            except Exception as e:
                blob_errors += 1
                logger.warning("Failed to delete blob %s: %s", rec.storage_path, e)

        q = delete(FileRecord).where(FileRecord.tenant_id == auth.tenant_id)
        result = await db.execute(q)
        deleted["files"] = result.rowcount
        if blob_errors:
            deleted["files_blob_errors"] = blob_errors

    # ── 5. evaluators ──
    if erase_all or "evaluators" in targets:
        q = delete(Evaluator).where(Evaluator.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(Evaluator.app_id == app_id)
        if not body.include_seed_data:
            q = q.where(
                ~((Evaluator.visibility == Visibility.APP) & (Evaluator.listing_id == None))
            )
        result = await db.execute(q)
        deleted["evaluators"] = result.rowcount

    # ── 6. prompts ──
    if erase_all or "prompts" in targets:
        q = delete(Prompt).where(Prompt.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(Prompt.app_id == app_id)
        if not body.include_seed_data:
            from app.constants import SYSTEM_TENANT_ID
            q = q.where(Prompt.tenant_id != SYSTEM_TENANT_ID)
        result = await db.execute(q)
        deleted["prompts"] = result.rowcount

    # ── 7. schemas ──
    if erase_all or "schemas" in targets:
        q = delete(Schema).where(Schema.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(Schema.app_id == app_id)
        if not body.include_seed_data:
            from app.constants import SYSTEM_TENANT_ID
            q = q.where(Schema.tenant_id != SYSTEM_TENANT_ID)
        result = await db.execute(q)
        deleted["schemas"] = result.rowcount

    # ── 8. settings ──
    if erase_all or "settings" in targets:
        q = delete(Setting).where(Setting.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(Setting.app_id == app_id)
        result = await db.execute(q)
        deleted["settings"] = result.rowcount

    # ── 9. tags ──
    if erase_all or "tags" in targets:
        q = delete(Tag).where(Tag.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(Tag.app_id == app_id)
        result = await db.execute(q)
        deleted["tags"] = result.rowcount

    # ── 10. jobs ──
    if erase_all or "jobs" in targets:
        q = delete(Job).where(Job.tenant_id == auth.tenant_id)
        result = await db.execute(q)
        deleted["jobs"] = result.rowcount

    # ── 11. history ──
    if erase_all or "history" in targets:
        q = delete(History).where(History.tenant_id == auth.tenant_id)
        if app_id:
            q = q.where(History.app_id == app_id)
        result = await db.execute(q)
        deleted["history"] = result.rowcount

    await db.commit()

    logger.warning("Admin erase complete: %s", deleted)
    return {"deleted": deleted}


# ── User Management ──────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    auth: AuthContext = require_permission('user:edit'),
    db: AsyncSession = Depends(get_db),
):
    """List all users in the tenant."""
    result = await db.execute(
        select(User).where(User.tenant_id == auth.tenant_id).order_by(User.created_at)
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "displayName": u.display_name,
            "roleId": str(u.role_id),
            "roleName": u.role.name,
            "isOwner": u.role.is_system and u.role.name == "Owner",
            "isActive": u.is_active,
            "createdAt": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    auth: AuthContext = require_permission('user:create'),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user in the tenant."""
    from app.auth.utils import hash_password

    # Enforce tenant domain policy
    from app.routes.auth import _check_allowed_domains, _validate_password_strength
    await _check_allowed_domains(body.email, auth.tenant_id, db)

    # Validate password strength
    strength_error = _validate_password_strength(body.password)
    if strength_error:
        raise HTTPException(400, detail=strength_error)

    # Check duplicate email
    existing = await db.scalar(
        select(User).where(User.tenant_id == auth.tenant_id, User.email == body.email)
    )
    if existing:
        raise HTTPException(400, "A user with this email already exists in this tenant")

    user = User(
        tenant_id=auth.tenant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role_id=_uuid.UUID(body.role_id),
    )
    db.add(user)
    await db.flush()

    await write_audit_log(
        db,
        tenant_id=auth.tenant_id,
        actor_id=auth.user_id,
        action="user:create",
        entity_type="user",
        entity_id=user.id,
        after_state={"email": user.email, "role_id": str(user.role_id)},
        request=request,
    )

    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "roleId": str(user.role_id),
        "roleName": user.role.name,
        "isOwner": user.role.is_system and user.role.name == "Owner",
        "isActive": user.is_active,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: _uuid.UUID,
    body: UpdateUserRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Update a user (name, role_id, is_active) within the tenant."""
    if not auth.is_owner:
        # Check what fields are being changed
        if body.role_id is not None and "role:assign" not in auth.permissions:
            raise HTTPException(403, "Missing permission: role:assign")
        needs_edit = (body.display_name is not None or body.is_active is not None)
        if needs_edit and "user:edit" not in auth.permissions:
            raise HTTPException(403, "Missing permission: user:edit")
        if not body.role_id and not needs_edit:
            raise HTTPException(403, "No permitted changes in request")

    user = await db.scalar(
        select(User).where(User.id == user_id, User.tenant_id == auth.tenant_id)
    )
    if not user:
        raise HTTPException(404, "User not found")

    before_state = {"role_id": str(user.role_id), "display_name": user.display_name, "is_active": user.is_active}

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role_id is not None:
        user.role_id = _uuid.UUID(body.role_id)
    if body.is_active is not None:
        user.is_active = body.is_active

    await write_audit_log(
        db,
        tenant_id=auth.tenant_id,
        actor_id=auth.user_id,
        action="user:update",
        entity_type="user",
        entity_id=user.id,
        before_state=before_state,
        after_state={"role_id": str(user.role_id), "display_name": user.display_name, "is_active": user.is_active},
        request=request,
    )

    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "roleId": str(user.role_id),
        "roleName": user.role.name,
        "isOwner": user.role.is_system and user.role.name == "Owner",
        "isActive": user.is_active,
    }


class AdminResetPasswordRequest(CamelModel):
    new_password: str


@router.put("/users/{user_id}/password")
async def admin_reset_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    request: Request,
    auth: AuthContext = require_permission('user:reset_password'),
    db: AsyncSession = Depends(get_db),
):
    """Reset a user's password (admin+). Revokes all their refresh tokens."""
    from app.routes.auth import _validate_password_strength

    strength_error = _validate_password_strength(body.new_password)
    if strength_error:
        raise HTTPException(400, detail=strength_error)

    user = await db.scalar(
        select(User).where(User.id == _uuid.UUID(user_id), User.tenant_id == auth.tenant_id)
    )
    if not user:
        raise HTTPException(404, "User not found")

    # Non-owners cannot reset owner passwords
    if user.role.is_system and user.role.name == "Owner" and not auth.is_owner:
        raise HTTPException(403, detail="Only owners can reset owner passwords")

    # Prevent reusing the same password
    from app.auth.utils import verify_password as _verify
    if _verify(body.new_password, user.password_hash):
        raise HTTPException(400, detail="New password must be different from current password")

    user.password_hash = hash_password(body.new_password)

    # Revoke all refresh tokens to force re-login
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user.id)
    )

    await write_audit_log(
        db,
        tenant_id=auth.tenant_id,
        actor_id=auth.user_id,
        action="user:reset_password",
        entity_type="user",
        entity_id=user.id,
        request=request,
    )

    await db.commit()
    return {"status": "ok", "id": user_id}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    request: Request,
    auth: AuthContext = require_permission('user:deactivate'),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a user. Does not delete data."""
    user = await db.scalar(
        select(User).where(User.id == _uuid.UUID(user_id), User.tenant_id == auth.tenant_id)
    )
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == auth.user_id:
        raise HTTPException(400, "Cannot deactivate yourself")

    user.is_active = False

    await write_audit_log(
        db,
        tenant_id=auth.tenant_id,
        actor_id=auth.user_id,
        action="user:deactivate",
        entity_type="user",
        entity_id=user.id,
        before_state={"is_active": True},
        after_state={"is_active": False},
        request=request,
    )

    await db.commit()
    return {"deactivated": True, "id": user_id}


# ── Tenant Management ────────────────────────────────────────────────────────

@router.get("/tenant")
async def get_tenant(
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant details (owner only)."""
    tenant = await db.scalar(select(Tenant).where(Tenant.id == auth.tenant_id))
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "isActive": tenant.is_active,
        "createdAt": tenant.created_at.isoformat() if tenant.created_at else None,
    }


@router.patch("/tenant")
async def update_tenant(
    body: UpdateTenantRequest,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant name (owner only)."""
    tenant = await db.scalar(select(Tenant).where(Tenant.id == auth.tenant_id))
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    if body.name is not None:
        tenant.name = body.name

    await db.commit()
    await db.refresh(tenant)
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "isActive": tenant.is_active,
    }


# ── Invite Links ─────────────────────────────────────────────────────────────


class CreateInviteLinkRequest(CamelModel):
    label: Optional[str] = None
    role_id: str
    max_uses: Optional[int] = None
    expires_in_hours: int = 168  # 7 days


def _invite_response(invite: InviteLink, creator_email: str) -> dict:
    return {
        "id": str(invite.id),
        "label": invite.label,
        "roleId": str(invite.role_id),
        "maxUses": invite.max_uses,
        "usesCount": invite.uses_count,
        "expiresAt": invite.expires_at.isoformat(),
        "isActive": invite.is_active,
        "createdAt": invite.created_at.isoformat() if invite.created_at else None,
        "createdByEmail": creator_email,
    }


@router.post("/invite-links", status_code=201)
async def create_invite_link(
    body: CreateInviteLinkRequest,
    request: Request,
    auth: AuthContext = require_permission('user:invite'),
    db: AsyncSession = Depends(get_db),
):
    """Generate an invite link for self-service signup (admin+)."""
    if body.expires_in_hours < 1 or body.expires_in_hours > 720:
        raise HTTPException(400, detail="Expiry must be between 1 and 720 hours")
    if body.max_uses is not None and body.max_uses < 1:
        raise HTTPException(400, detail="Max uses must be at least 1")

    raw_token, token_hash = create_refresh_token()  # reuse same random+hash pattern

    invite = InviteLink(
        tenant_id=auth.tenant_id,
        created_by=auth.user_id,
        token_hash=token_hash,
        label=body.label,
        role_id=_uuid.UUID(body.role_id),
        max_uses=body.max_uses,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours),
    )
    db.add(invite)
    await db.flush()

    await write_audit_log(
        db,
        tenant_id=auth.tenant_id,
        actor_id=auth.user_id,
        action="invite_link:create",
        entity_type="invite_link",
        entity_id=invite.id,
        after_state={"label": invite.label, "role_id": str(invite.role_id)},
        request=request,
    )

    await db.commit()
    await db.refresh(invite)

    # Build the invite URL from the configured frontend base URL
    from app.config import settings
    base = settings.APP_BASE_URL.rstrip("/")
    invite_url = f"{base}/signup?invite={raw_token}"

    resp = _invite_response(invite, auth.email)
    resp["inviteUrl"] = invite_url
    return resp


@router.get("/invite-links")
async def list_invite_links(
    auth: AuthContext = require_permission('user:invite'),
    db: AsyncSession = Depends(get_db),
):
    """List all invite links for the tenant (admin+)."""
    result = await db.execute(
        select(InviteLink, User.email)
        .join(User, InviteLink.created_by == User.id)
        .where(InviteLink.tenant_id == auth.tenant_id)
        .order_by(InviteLink.created_at.desc())
    )
    return [_invite_response(invite, email) for invite, email in result.all()]


@router.delete("/invite-links/{link_id}")
async def revoke_invite_link(
    link_id: str,
    request: Request,
    auth: AuthContext = require_permission('user:invite'),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an invite link (admin+)."""
    invite = await db.scalar(
        select(InviteLink).where(
            InviteLink.id == _uuid.UUID(link_id),
            InviteLink.tenant_id == auth.tenant_id,
        )
    )
    if not invite:
        raise HTTPException(404, detail="Invite link not found")

    invite.is_active = False

    await write_audit_log(
        db,
        tenant_id=auth.tenant_id,
        actor_id=auth.user_id,
        action="invite_link:revoke",
        entity_type="invite_link",
        entity_id=invite.id,
        before_state={"is_active": True},
        after_state={"is_active": False},
        request=request,
    )

    await db.commit()
    return {"revoked": True, "id": link_id}


# ── Tenant Config ─────────────────────────────────────────────────────────────


class UpdateTenantConfigRequest(CamelModel):
    app_url: Optional[str] = None
    logo_url: Optional[str] = None
    allowed_domains: Optional[list[str]] = None


def _tenant_config_response(config: TenantConfig) -> dict:
    return {
        "id": str(config.id),
        "tenantId": str(config.tenant_id),
        "appUrl": config.app_url,
        "logoUrl": config.logo_url,
        "allowedDomains": config.allowed_domains or [],
        "createdAt": config.created_at.isoformat() if config.created_at else None,
        "updatedAt": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.get("/tenant-config")
async def get_tenant_config(
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant config (owner only). Creates default config if none exists."""
    config = await db.scalar(
        select(TenantConfig).where(TenantConfig.tenant_id == auth.tenant_id)
    )
    if not config:
        config = TenantConfig(tenant_id=auth.tenant_id)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return _tenant_config_response(config)


@router.patch("/tenant-config")
async def update_tenant_config(
    body: UpdateTenantConfigRequest,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant config (owner only)."""
    config = await db.scalar(
        select(TenantConfig).where(TenantConfig.tenant_id == auth.tenant_id)
    )
    if not config:
        config = TenantConfig(tenant_id=auth.tenant_id)
        db.add(config)
        await db.flush()

    if body.app_url is not None:
        config.app_url = body.app_url or None
    if body.logo_url is not None:
        config.logo_url = body.logo_url or None
    if body.allowed_domains is not None:
        # Normalize: lowercase, ensure @ prefix
        config.allowed_domains = [
            d.lower() if d.startswith("@") else f"@{d.lower()}"
            for d in body.allowed_domains
            if d.strip()
        ]

    await db.commit()
    await db.refresh(config)
    return _tenant_config_response(config)
