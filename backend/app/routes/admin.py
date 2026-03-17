"""Admin API routes — database stats, selective data erasure, user management, tenant management."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, require_admin, require_owner
from app.database import get_db
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
from app.models.tag import Tag
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.schemas.base import CamelModel

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
    role: str = "member"


class UpdateUserRequest(CamelModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UpdateTenantRequest(CamelModel):
    name: Optional[str] = None


# ── GET /api/admin/stats ──────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    app_id: Optional[str] = None,
    auth: AuthContext = Depends(require_admin),
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
            (Evaluator.is_global == True) & (Evaluator.listing_id == None),
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
            (Evaluator.is_global == True) & (Evaluator.listing_id == None),
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
                ~((Evaluator.is_global == True) & (Evaluator.listing_id == None))
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
    auth: AuthContext = Depends(require_admin),
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
            "role": u.role.value,
            "isActive": u.is_active,
            "createdAt": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user in the tenant."""
    from app.auth.utils import hash_password

    # Check duplicate email
    existing = await db.scalar(
        select(User).where(User.tenant_id == auth.tenant_id, User.email == body.email)
    )
    if existing:
        raise HTTPException(400, "A user with this email already exists in this tenant")

    try:
        role = UserRole(body.role)
    except ValueError:
        raise HTTPException(400, f"Invalid role: {body.role}")

    user = User(
        tenant_id=auth.tenant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "role": user.role.value,
        "isActive": user.is_active,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a user (name, role, is_active) within the tenant."""
    from uuid import UUID
    user = await db.scalar(
        select(User).where(User.id == UUID(user_id), User.tenant_id == auth.tenant_id)
    )
    if not user:
        raise HTTPException(404, "User not found")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        try:
            user.role = UserRole(body.role)
        except ValueError:
            raise HTTPException(400, f"Invalid role: {body.role}")
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "role": user.role.value,
        "isActive": user.is_active,
    }


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a user (owner only). Does not delete data."""
    from uuid import UUID
    user = await db.scalar(
        select(User).where(User.id == UUID(user_id), User.tenant_id == auth.tenant_id)
    )
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == auth.user_id:
        raise HTTPException(400, "Cannot deactivate yourself")

    user.is_active = False
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
