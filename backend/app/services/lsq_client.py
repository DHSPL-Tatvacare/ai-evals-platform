"""LeadSquared API client for Inside Sales call data."""

import asyncio
import json
import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

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
            if isinstance(data, dict) and data.get("List"):
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
        "phoneNumber": source_data.get("SourceNumber", "") if event_code == 21 else source_data.get("DestinationNumber", ""),
        "displayNumber": raw.get("mx_Custom_1", ""),
        "callNotes": source_data.get("CallNotes", ""),
        "callSessionId": source_data.get("CallSessionId", ""),
        "createdOn": raw.get("CreatedOn", ""),
    }


async def fetch_lead_by_id(prospect_id: str) -> dict[str, str]:
    """Fetch a single lead from LSQ by prospect ID.

    GET /v2/LeadManagement.svc/Leads.GetById?id=<prospectId>
    Returns: {"firstName": str, "lastName": str, "phone": str, "email": str}
    """
    if not prospect_id:
        return {}

    async with httpx.AsyncClient(timeout=30) as client:
        url = f"{LSQ_BASE_URL}/LeadManagement.svc/Leads.GetById"
        params = {**_auth_params(), "id": prospect_id}
        try:
            resp = await _rate_limited_request(client, "GET", url, params=params)
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                lead = data[0]
                return {
                    "firstName": lead.get("FirstName") or "",
                    "lastName": lead.get("LastName") or "",
                    "phone": lead.get("Phone") or "",
                    "email": lead.get("EmailAddress") or "",
                }
        except Exception as e:
            logger.warning("Lead fetch failed for %s: %s", prospect_id, e)

    return {}
