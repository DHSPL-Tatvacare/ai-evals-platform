"""Routes for Inside Sales call data."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.database import get_db
from app.schemas.inside_sales import CallRecord, CallListResponse
from app.services.lsq_client import (
    fetch_call_activities,
    normalize_activity,
    hydrate_leads_bulk,
    get_cached_calls,
    cache_calls,
    call_cache,
)

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
    db: AsyncSession = Depends(get_db),
):
    """Fetch call activities from LSQ with cached lead hydration."""
    # Parse event codes
    codes = None
    if event_codes:
        codes = [int(c.strip()) for c in event_codes.split(",")]

    # Step 1: Fetch activity list from LSQ (1-2 API calls — not the bottleneck)
    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        event_codes=codes,
        page=page,
        page_size=page_size,
    )

    # Step 2: Normalize
    all_calls = [normalize_activity(a) for a in result["activities"]]

    # Step 3: Apply filters
    if agent:
        all_calls = [c for c in all_calls if agent.lower() in c["agentName"].lower()]
    if direction:
        all_calls = [c for c in all_calls if c["direction"] == direction]
    if status:
        all_calls = [c for c in all_calls if c["status"].lower() == status.lower()]

    tenant_key = str(auth.tenant_id)
    final_calls: list[dict] = []
    uncached_calls: list[dict] = []

    # Step 4: Check L1 in-memory cache
    for call in all_calls:
        aid = call["activityId"]
        l1_key = (tenant_key, aid)
        if l1_key in call_cache:
            final_calls.append(call_cache[l1_key])
        else:
            uncached_calls.append(call)

    # Step 5: Check L2 DB cache for L1 misses
    if uncached_calls:
        uncached_ids = [c["activityId"] for c in uncached_calls]
        db_cached = await get_cached_calls(db, auth.tenant_id, uncached_ids)

        still_uncached: list[dict] = []
        for call in uncached_calls:
            aid = call["activityId"]
            if aid in db_cached:
                cached_call = db_cached[aid]
                call_cache[(tenant_key, aid)] = cached_call  # promote to L1
                final_calls.append(cached_call)
            else:
                still_uncached.append(call)

        # Step 6: Bulk hydrate remaining misses
        if still_uncached:
            prospect_ids = list(set(
                c["prospectId"] for c in still_uncached if c["prospectId"]
            ))
            lead_map = await hydrate_leads_bulk(prospect_ids)

            for call in still_uncached:
                pid = call["prospectId"]
                if pid in lead_map:
                    lead = lead_map[pid]
                    first = lead.get("firstName", "")
                    last = lead.get("lastName", "")
                    call["leadName"] = f"{first} {last}".strip() or pid[:8]
                    # Use LSQ lead phone if we didn't get one from SourceData
                    if not call["phoneNumber"] and lead.get("phone"):
                        call["phoneNumber"] = lead["phone"]
                else:
                    call["leadName"] = pid[:8] if pid else ""

                call_cache[(tenant_key, call["activityId"])] = call
                final_calls.append(call)

            # Write all newly hydrated calls to DB cache (non-fatal)
            await cache_calls(db, auth.tenant_id, auth.user_id, still_uncached)

    return CallListResponse(
        calls=[CallRecord(**c) for c in final_calls],
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get("/calls/{activity_id}")
async def get_call(
    activity_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Get a single call detail by activity ID.

    For now, the listing data is sufficient — single call fetch
    will be implemented when call detail page needs it.
    When implemented, should check DB cache first via get_cached_calls.
    """
    return {"detail": "not yet implemented"}
