"""LeadSquared API client for Inside Sales call data."""

import asyncio
import json
import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# In-memory lead name cache (process-lifetime)
_lead_cache: dict[str, str] = {}

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


async def hydrate_lead_names(
    prospect_ids: list[str],
) -> dict[str, str]:
    """Bulk fetch lead names for prospect IDs. Uses cache."""
    uncached = [pid for pid in prospect_ids if pid and pid not in _lead_cache]

    if uncached:
        async with httpx.AsyncClient(timeout=30) as client:
            # Batch in groups of 50
            for i in range(0, len(uncached), 50):
                batch = uncached[i : i + 50]
                url = f"{LSQ_BASE_URL}/Leads.svc/Leads.GetByIds"
                params = {**_auth_params(), "ids": ",".join(batch)}
                try:
                    resp = await _rate_limited_request(
                        client, "GET", url, params=params
                    )
                    leads = resp.json()
                    if isinstance(leads, list):
                        for lead in leads:
                            pid = lead.get("ProspectID", "")
                            name = lead.get("FirstName", "")
                            last = lead.get("LastName", "")
                            full = f"{name} {last}".strip() or pid[:8]
                            _lead_cache[pid] = full
                except Exception as e:
                    logger.warning("Lead hydration failed for batch: %s", e)
                    for pid in batch:
                        _lead_cache[pid] = pid[:8]  # Fallback to truncated ID

    return {pid: _lead_cache.get(pid, pid[:8]) for pid in prospect_ids}
