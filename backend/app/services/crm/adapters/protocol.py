"""CRM-source adapter contract — adapters ONLY land raw + discover, never shape a serving row."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol


@dataclass(frozen=True)
class SourceRecordDraft:
    """A provider record shaped for landing; tenant/app/connection scope is added by the landing job."""

    source_object: str
    record_type: str
    source_record_id: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class DiscoveredObject:
    """One mappable source object plus the field names discovered from sample data."""

    source_object: str
    record_type: str
    fields: list[str]


@dataclass(frozen=True)
class FetchPage:
    """One page of landing drafts plus paging state the sync job loops on."""

    records: list[SourceRecordDraft]
    next_watermark: str | None
    has_more: bool


class CrmTransport(Protocol):
    """The HTTP seam — faked in tests so adapter logic runs against verbatim fixtures."""

    async def post(
        self, *, base_url: str, path: str, params: dict[str, str], json: dict[str, Any]
    ) -> Any: ...


class CrmSourceAdapter(Protocol):
    """Provider-aware CRM ingestion: discover mappable objects + fetch raw records to land."""

    capability: ClassVar[str]
    vendor: ClassVar[str]

    async def discover_objects(
        self, *, creds: dict[str, Any], sample_size: int = 50
    ) -> list[DiscoveredObject]: ...

    async def fetch_records(
        self,
        *,
        creds: dict[str, Any],
        source_object: str,
        watermark: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> FetchPage: ...


__all__ = [
    "CrmSourceAdapter",
    "CrmTransport",
    "DiscoveredObject",
    "FetchPage",
    "SourceRecordDraft",
]
