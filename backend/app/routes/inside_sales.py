"""Routes for Inside Sales call data."""

import uuid as _uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth.context import AuthContext, get_auth_context
from app.database import get_db
from app.schemas.inside_sales import CallRecord, CallListResponse, LeadDetailResponse
from app.services.lsq_client import fetch_call_activities, normalize_activity, fetch_lead_by_id

router = APIRouter(prefix="/api/inside-sales", tags=["inside-sales"])


@router.get("/calls", response_model=CallListResponse)
async def list_calls(
    date_from: str = Query(..., description="Start date YYYY-MM-DD HH:MM:SS"),
    date_to: str = Query(..., description="End date YYYY-MM-DD HH:MM:SS"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    agent: str | None = Query(None),
    direction: str | None = Query(None),
    status: str | None = Query(None),
    event_codes: str | None = Query(None, description="Comma-separated event codes"),
    auth: AuthContext = Depends(get_auth_context),
):
    """Fetch call activities from LSQ. Activity-only — no lead hydration."""
    codes = None
    if event_codes:
        codes = [int(c.strip()) for c in event_codes.split(",")]

    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        event_codes=codes,
        page=page,
        page_size=page_size,
    )

    calls = [normalize_activity(a) for a in result["activities"]]

    if agent:
        calls = [c for c in calls if agent.lower() in c["agentName"].lower()]
    if direction:
        calls = [c for c in calls if c["direction"] == direction]
    if status:
        calls = [c for c in calls if c["status"].lower() == status.lower()]

    return CallListResponse(
        calls=[CallRecord(**c) for c in calls],
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get("/leads/{prospect_id}", response_model=LeadDetailResponse)
async def get_lead(
    prospect_id: str,
    refresh: bool = Query(False, description="Force re-fetch from LSQ"),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Fetch lead details by prospect ID. Cached in DB after first fetch.

    Pass ?refresh=true to force re-fetch from LSQ (resync button).
    """
    from app.models.lsq_call_cache import LsqLeadCache

    # Check DB cache first (unless refresh requested)
    if not refresh:
        result = await db.execute(
            select(LsqLeadCache).where(
                LsqLeadCache.tenant_id == auth.tenant_id,
                LsqLeadCache.prospect_id == prospect_id,
            )
        )
        cached = result.scalar_one_or_none()
        if cached:
            return LeadDetailResponse(
                prospect_id=prospect_id,
                first_name=cached.first_name,
                last_name=cached.last_name,
                phone=cached.phone,
                email=cached.email,
                cached=True,
            )

    # Fetch from LSQ
    lead = await fetch_lead_by_id(prospect_id)

    # Cache the result (upsert)
    try:
        stmt = pg_insert(LsqLeadCache).values(
            id=_uuid.uuid4(),
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            prospect_id=prospect_id,
            first_name=lead.get("firstName", ""),
            last_name=lead.get("lastName", ""),
            phone=lead.get("phone", ""),
            email=lead.get("email", ""),
        ).on_conflict_do_update(
            constraint="uq_lsq_lead_cache_tenant_prospect",
            set_={
                "first_name": lead.get("firstName", ""),
                "last_name": lead.get("lastName", ""),
                "phone": lead.get("phone", ""),
                "email": lead.get("email", ""),
            },
        )
        await db.execute(stmt)
        await db.commit()
    except Exception:
        await db.rollback()

    return LeadDetailResponse(
        prospect_id=prospect_id,
        first_name=lead.get("firstName", ""),
        last_name=lead.get("lastName", ""),
        phone=lead.get("phone", ""),
        email=lead.get("email", ""),
        cached=False,
    )
