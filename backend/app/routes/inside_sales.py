"""Routes for Inside Sales call data."""

from fastapi import APIRouter, Depends, Query

from app.auth.context import AuthContext, get_auth_context
from app.schemas.inside_sales import CallRecord, CallListResponse
from app.services.lsq_client import (
    fetch_call_activities,
    normalize_activity,
    hydrate_lead_names,
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
):
    """Fetch call activities from LSQ with lead name hydration."""
    # Parse event codes
    codes = None
    if event_codes:
        codes = [int(c.strip()) for c in event_codes.split(",")]

    # Fetch from LSQ
    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        event_codes=codes,
        page=page,
        page_size=page_size,
    )

    # Normalize activities
    calls = [normalize_activity(a) for a in result["activities"]]

    # Apply filters (LSQ API doesn't support all our filter needs)
    if agent:
        calls = [c for c in calls if agent.lower() in c["agentName"].lower()]
    if direction:
        calls = [c for c in calls if c["direction"] == direction]
    if status:
        calls = [c for c in calls if c["status"].lower() == status.lower()]

    # Hydrate lead names
    prospect_ids = [c["prospectId"] for c in calls if c["prospectId"]]
    name_map = await hydrate_lead_names(prospect_ids)
    for call in calls:
        call["leadName"] = name_map.get(call["prospectId"], "")

    return CallListResponse(
        calls=[CallRecord(**c) for c in calls],
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
    """
    return {"detail": "not yet implemented"}
