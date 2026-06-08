"""LeadSquared CRM-source adapter — lands leads + call activities, discovers their fields.

Provider-truth ingestion: fields come from what LSQ actually returns (no hardcoded
column list), so a tenant's custom ``mx_*`` fields surface for mapping. Auth is by
``accessKey`` + ``secretKey`` query params against the connection's ``region_host``.
The adapter shapes landing drafts only — it never writes a serving row.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.crm.adapters.protocol import (
    CrmTransport,
    DiscoveredObject,
    FetchPage,
    SourceRecordDraft,
)

_LEADS_PATH = "LeadManagement.svc/Leads.Get"
_ACTIVITY_PATH = "ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent"
_CALL_EVENT_CODES = (21, 22)  # 21 = inbound call, 22 = outbound call
_WATERMARK_FLOOR = "2000-01-01 00:00:00"


def lsq_lead_draft(raw: dict[str, Any]) -> SourceRecordDraft:
    return SourceRecordDraft(
        source_object="Lead",
        record_type="lead",
        source_record_id=str(raw.get("ProspectID") or ""),
        raw_payload=raw,
    )


def lsq_activity_draft(raw: dict[str, Any]) -> SourceRecordDraft:
    return SourceRecordDraft(
        source_object="Activity",
        record_type="activity",
        source_record_id=str(raw.get("ProspectActivityId") or ""),
        raw_payload=raw,
    )


def _now_lsq() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _max_field(records: list[dict[str, Any]], field: str) -> str | None:
    values = [str(r.get(field)) for r in records if r.get(field)]
    return max(values) if values else None


def _fields_of(records: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for r in records:
        names.update(r.keys())
    return sorted(names)


class _HttpxTransport:
    async def post(
        self, *, base_url: str, path: str, params: dict[str, str], json: dict[str, Any]
    ) -> Any:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, params=params, json=json)
            resp.raise_for_status()
            return resp.json()


class LsqCrmSourceAdapter:
    capability = "crm_source"
    vendor = "lsq"

    def __init__(self, *, transport: CrmTransport | None = None) -> None:
        self._transport = transport or _HttpxTransport()

    @staticmethod
    def _auth(creds: dict[str, Any]) -> tuple[str, dict[str, str]]:
        return (
            str(creds.get("region_host", "")).rstrip("/"),
            {
                "accessKey": str(creds.get("access_key", "")),
                "secretKey": str(creds.get("secret_key", "")),
            },
        )

    async def _get_leads(
        self, creds: dict[str, Any], *, watermark: str | None, page: int, page_size: int
    ) -> list[dict[str, Any]]:
        base, params = self._auth(creds)
        body = {
            "Parameter": {
                "LookupName": "ModifiedOn",
                "LookupValue": watermark or _WATERMARK_FLOOR,
                "SqlOperator": ">=",
            },
            "Paging": {"PageIndex": page - 1, "PageSize": page_size},
            "Sorting": {"ColumnName": "ModifiedOn", "Direction": 1},
        }
        data = await self._transport.post(base_url=base, path=_LEADS_PATH, params=params, json=body)
        return data if isinstance(data, list) else []

    async def _get_activities(
        self, creds: dict[str, Any], *, event_code: int, watermark: str | None, page: int, page_size: int
    ) -> list[dict[str, Any]]:
        base, params = self._auth(creds)
        body = {
            "Parameter": {
                "FromDate": watermark or _WATERMARK_FLOOR,
                "ToDate": _now_lsq(),
                "ActivityEvent": event_code,
            },
            "Paging": {"PageIndex": page, "PageSize": page_size},
            "Sorting": {"ColumnName": "CreatedOn", "Direction": 1},
        }
        data = await self._transport.post(base_url=base, path=_ACTIVITY_PATH, params=params, json=body)
        if isinstance(data, dict):
            return list(data.get("List") or [])
        return data if isinstance(data, list) else []

    async def discover_objects(
        self, *, creds: dict[str, Any], sample_size: int = 50
    ) -> list[DiscoveredObject]:
        leads = await self._get_leads(creds, watermark=None, page=1, page_size=sample_size)
        activities: list[dict[str, Any]] = []
        for code in _CALL_EVENT_CODES:
            activities.extend(
                await self._get_activities(creds, event_code=code, watermark=None, page=1, page_size=sample_size)
            )
        return [
            DiscoveredObject(source_object="Lead", record_type="lead", fields=_fields_of(leads)),
            DiscoveredObject(source_object="Activity", record_type="activity", fields=_fields_of(activities)),
        ]

    async def fetch_records(
        self,
        *,
        creds: dict[str, Any],
        source_object: str,
        watermark: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> FetchPage:
        if source_object == "Lead":
            leads = await self._get_leads(creds, watermark=watermark, page=page, page_size=page_size)
            return FetchPage(
                records=[lsq_lead_draft(l) for l in leads],
                next_watermark=_max_field(leads, "ModifiedOn"),
                has_more=len(leads) >= page_size,
            )
        if source_object == "Activity":
            collected: list[dict[str, Any]] = []
            has_more = False
            for code in _CALL_EVENT_CODES:
                rows = await self._get_activities(
                    creds, event_code=code, watermark=watermark, page=page, page_size=page_size
                )
                collected.extend(rows)
                has_more = has_more or len(rows) >= page_size
            return FetchPage(
                records=[lsq_activity_draft(a) for a in collected],
                next_watermark=_max_field(collected, "CreatedOn"),
                has_more=has_more,
            )
        raise ValueError(f"lsq adapter has no source object {source_object!r}")


from app.services.orchestration.adapters import register_adapter  # noqa: E402

register_adapter(capability="crm_source", vendor="lsq", adapter=LsqCrmSourceAdapter())

__all__ = ["LsqCrmSourceAdapter", "lsq_activity_draft", "lsq_lead_draft"]
