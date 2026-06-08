"""CRM ingestion API schemas (camelCase JSON) — discovery, field maps, jobs, sync activity."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.schemas.base import CamelModel


class StandardColumnOut(CamelModel):
    target: str
    label: str
    data_type: str


class GrainSchemaOut(CamelModel):
    record_type: str
    natural_key_target: str
    lead_link_target: str
    lead_link_required: bool
    expected_targets: list[str]
    standard_columns: list[StandardColumnOut]
    slots: dict[str, list[str]]


class GrainsResponse(CamelModel):
    grains: list[GrainSchemaOut]


class FieldValuesResponse(CamelModel):
    field: str
    values: list[str]


class DiscoveredObjectOut(CamelModel):
    source_object: str
    record_type: str
    fields: list[str]


class DiscoverResponse(CamelModel):
    objects: list[DiscoveredObjectOut]


class FieldBindingIn(CamelModel):
    slot: str
    semantic_key: str
    source_field: str
    data_type: str = "text"
    value_map: Optional[dict[str, Any]] = None
    description: Optional[str] = None


class FieldMapPublishRequest(CamelModel):
    record_type: str
    bindings: list[FieldBindingIn]


class FieldBindingOut(CamelModel):
    slot: str
    semantic_key: str
    source_field: str
    data_type: str
    value_map: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    version: int


class FieldMapResponse(CamelModel):
    record_type: str
    version: int
    bindings: list[FieldBindingOut]


class FieldMapPublishResponse(CamelModel):
    record_type: str
    version: int
    unpack_job_id: str


class SyncRequest(CamelModel):
    source_objects: Optional[list[str]] = None


class JobSubmittedResponse(CamelModel):
    job_id: str
    status: str


class SyncActivityOut(CamelModel):
    id: str
    source_family: str
    sync_mode: str
    status: str
    records_scanned: int
    records_upserted: int
    records_failed: int
    watermark_to: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SyncActivityResponse(CamelModel):
    runs: list[SyncActivityOut]
