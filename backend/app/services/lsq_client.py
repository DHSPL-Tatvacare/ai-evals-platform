"""LeadSquared API client for Inside Sales call data."""

import asyncio
import json
import os
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

# In-memory L1 cache: (tenant_id, activity_id) → full call dict
# Note: unbounded growth within process lifetime. Acceptable because
# page_size is capped at 100 and typical daily call volume is <5000.
call_cache: dict[tuple[str, str], dict[str, Any]] = {}

LSQ_BASE_URL = os.getenv("LSQ_BASE_URL", "https://api-in21.leadsquared.com/v2")
LSQ_ACCESS_KEY = os.getenv("LSQ_ACCESS_KEY", "")
LSQ_SECRET_KEY = os.getenv("LSQ_SECRET_KEY", "")

# Rate limit: 25 requests per 5 seconds → semaphore + delay
_rate_semaphore = asyncio.Semaphore(5)


def _auth_params() -> dict[str, str]:
    return {"accessKey": LSQ_ACCESS_KEY, "secretKey": LSQ_SECRET_KEY}


async def _rate_limited_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with rate limiting."""
    async with _rate_semaphore:
        resp = await client.request(method, url, **kwargs)
        resp.raise_for_status()
        await asyncio.sleep(0.2)  # 200ms spacing
        return resp


async def fetch_call_activities(
    date_from: str,
    date_to: str,
    event_codes: list[int] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Fetch phone call activities from LSQ.

    Returns: { "activities": [...], "total": int }
    """
    if event_codes is None:
        event_codes = [21, 22]  # Inbound + Outbound system telephony

    all_activities: list[dict[str, Any]] = []
    total_record_count = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for event_code in event_codes:
            url = f"{LSQ_BASE_URL}/ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent"
            body = {
                "Parameter": {
                    "FromDate": date_from,
                    "ToDate": date_to,
                    "ActivityEvent": event_code,
                },
                "Paging": {
                    "PageIndex": page,
                    "PageSize": page_size,
                },
                "Sorting": {
                    "ColumnName": "CreatedOn",
                    "Direction": 1,  # Descending
                },
            }
            resp = await _rate_limited_request(
                client, "POST", url, params=_auth_params(), json=body
            )
            data = resp.json()
            if isinstance(data, dict) and "List" in data:
                all_activities.extend(data["List"])
                total_record_count += data.get("RecordCount", len(data["List"]))
            elif isinstance(data, list):
                all_activities.extend(data)
                total_record_count += len(data)

    return {"activities": all_activities, "total": total_record_count}


def _parse_source_data(note: str) -> dict[str, Any]:
    """Parse ActivityEvent_Note to extract SourceData JSON."""
    try:
        if "SourceData" in note:
            start = note.index('{"')
            brace_count = 0
            for i, c in enumerate(note[start:], start):
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                if brace_count == 0:
                    return json.loads(note[start : i + 1])
        return {}
    except (ValueError, json.JSONDecodeError):
        return {}


def normalize_activity(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw LSQ activity into a clean call record."""
    source_data = _parse_source_data(raw.get("ActivityEvent_Note", ""))
    event_code = int(raw.get("ActivityEvent", 0))

    return {
        "activityId": raw.get("ProspectActivityId", ""),
        "prospectId": raw.get("RelatedProspectId", ""),
        "agentName": raw.get("CreatedByName", ""),
        "agentEmail": raw.get("CreatedByEmailAddress", ""),
        "eventCode": event_code,
        "direction": "inbound" if event_code == 21 else "outbound",
        "status": raw.get("Status", ""),
        "callStartTime": raw.get("mx_Custom_2", ""),
        "durationSeconds": int(raw.get("mx_Custom_3", 0) or 0),
        "recordingUrl": raw.get("mx_Custom_4", ""),
        "phoneNumber": source_data.get("DestinationNumber", ""),
        "displayNumber": raw.get("mx_Custom_1", ""),
        "callNotes": source_data.get("CallNotes", ""),
        "callSessionId": source_data.get("CallSessionId", ""),
        "createdOn": raw.get("CreatedOn", ""),
        "leadName": "",  # Hydrated separately
    }


async def hydrate_leads_bulk(
    prospect_ids: list[str],
) -> dict[str, dict[str, str]]:
    """Fetch lead names + phone for prospect IDs via LSQ bulk endpoint.

    POST /v2/LeadManagement.svc/Leads/Retrieve/ByIds
    Request: {"SearchParameters": {"LeadIds": [...]}, "Columns": {"Include_CSV": "..."}, "Paging": {...}}
    Response: {"RecordCount": N, "Leads": [{...}, ...]}
    Returns: { prospect_id: {"firstName": str, "lastName": str, "phone": str} }
    """
    unique_ids = list(set(pid for pid in prospect_ids if pid))
    if not unique_ids:
        return {}

    result: dict[str, dict[str, str]] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # LSQ bulk endpoint accepts up to 10,000 IDs but we batch at 100
        # to stay well within rate limits (bulk APIs: 5 req/5s on Pro plan)
        batch_size = 100
        for i in range(0, len(unique_ids), batch_size):
            batch = unique_ids[i : i + batch_size]
            url = f"{LSQ_BASE_URL}/LeadManagement.svc/Leads/Retrieve/ByIds"
            body = {
                "SearchParameters": {
                    "LeadIds": batch,
                },
                "Columns": {
                    "Include_CSV": "ProspectId,FirstName,LastName,Phone",
                },
                "Paging": {
                    "PageIndex": 1,
                    "PageSize": len(batch),
                },
            }
            try:
                resp = await _rate_limited_request(
                    client, "POST", url, params=_auth_params(), json=body
                )
                data = resp.json()
                leads: list[dict] = []
                if isinstance(data, dict) and "Leads" in data:
                    leads = data["Leads"]
                elif isinstance(data, list):
                    leads = data

                if leads:
                    # Check if ProspectId is returned in the response
                    has_prospect_id = "ProspectId" in leads[0]

                    if has_prospect_id:
                        for lead in leads:
                            pid = lead.get("ProspectId", "")
                            if pid:
                                result[pid] = {
                                    "firstName": lead.get("FirstName") or "",
                                    "lastName": lead.get("LastName") or "",
                                    "phone": lead.get("Phone") or "",
                                }
                    else:
                        # Fallback: if ProspectId not in response, match by input order
                        # This is a defensive fallback — log a warning so we know
                        logger.warning(
                            "Bulk lead response missing ProspectId field. "
                            "Response keys: %s. Falling back to index matching.",
                            list(leads[0].keys()) if leads else "empty",
                        )
                        for idx, lead in enumerate(leads):
                            if idx < len(batch):
                                pid = batch[idx]
                                result[pid] = {
                                    "firstName": lead.get("FirstName") or "",
                                    "lastName": lead.get("LastName") or "",
                                    "phone": lead.get("Phone") or "",
                                }
            except Exception as e:
                logger.warning(
                    "Bulk lead hydration failed for batch of %d: %s",
                    len(batch), e,
                )

    return result


async def get_cached_calls(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    activity_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch cached call records from DB. Returns {activity_id: call_dict}."""
    if not activity_ids:
        return {}

    from app.models.lsq_call_cache import LsqCallCache

    result = await db.execute(
        select(LsqCallCache).where(
            LsqCallCache.tenant_id == tenant_id,
            LsqCallCache.activity_id.in_(activity_ids),
        )
    )
    rows = result.scalars().all()

    cached: dict[str, dict[str, Any]] = {}
    for row in rows:
        cached[row.activity_id] = {
            "activityId": row.activity_id,
            "prospectId": row.prospect_id,
            "agentName": row.agent_name,
            "agentEmail": row.agent_email,
            "eventCode": row.event_code,
            "direction": row.direction,
            "status": row.status,
            "callStartTime": row.call_start_time,
            "durationSeconds": row.duration_seconds,
            "recordingUrl": row.recording_url,
            "phoneNumber": row.phone_number,
            "displayNumber": row.display_number,
            "callNotes": row.call_notes,
            "callSessionId": row.call_session_id,
            "createdOn": row.created_on,
            "leadName": row.lead_name,
        }
    return cached


async def cache_calls(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    calls: list[dict[str, Any]],
) -> None:
    """Persist fully-hydrated call records to DB cache.

    Non-fatal: logs warning on failure, does not propagate exceptions.
    Uses INSERT ON CONFLICT DO NOTHING — if the row already exists
    (same tenant_id + activity_id), it is left as-is. This is correct
    because call records are immutable.
    """
    if not calls:
        return

    from app.models.lsq_call_cache import LsqCallCache

    try:
        for call in calls:
            stmt = pg_insert(LsqCallCache).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                activity_id=call["activityId"],
                prospect_id=call["prospectId"],
                agent_name=call["agentName"],
                agent_email=call["agentEmail"],
                event_code=call["eventCode"],
                direction=call["direction"],
                status=call["status"],
                call_start_time=call["callStartTime"],
                duration_seconds=call["durationSeconds"],
                recording_url=call["recordingUrl"],
                phone_number=call["phoneNumber"],
                display_number=call["displayNumber"],
                call_notes=call["callNotes"],
                call_session_id=call["callSessionId"],
                created_on=call["createdOn"],
                lead_name=call["leadName"],
            ).on_conflict_do_nothing(
                constraint="uq_lsq_call_cache_tenant_activity"
            )
            await db.execute(stmt)

        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning("Failed to cache LSQ calls: %s", e)
