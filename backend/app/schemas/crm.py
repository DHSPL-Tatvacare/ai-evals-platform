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


class ResolvedPreviewResponse(CamelModel):
    """A sample of the per-tenant resolved matview — the 'what Sherlock will see' editor panel."""
    record_type: str
    columns: list[str]
    rows: list[dict[str, Any]]


class DatasetSummary(CamelModel):
    """One record_type a connection exposes + its definition lifecycle state (drives the left rail)."""
    record_type: str
    source_object: str
    status: str
    version: int
    has_schedule: bool
    last_sync_at: Optional[datetime] = None


class DatasetsResponse(CamelModel):
    datasets: list[DatasetSummary]


class RawSampleRecordOut(CamelModel):
    source_record_id: str
    raw_payload: dict[str, Any]


class RawSampleResponse(CamelModel):
    record_type: str
    source_object: str
    records: list[RawSampleRecordOut]


class UnpackedSampleResponse(CamelModel):
    """Sample run through the DRAFT map without persisting — the 'Unpacked' toggle."""
    record_type: str
    columns: list[str]
    rows: list[dict[str, Any]]


class FilterableFieldOut(CamelModel):
    field: str
    operators: list[str]
    pushable: bool


class FilterCapabilityResponse(CamelModel):
    record_type: str
    source_object: str
    fields: list[FilterableFieldOut]


class DraftDefinitionRequest(CamelModel):
    """Draft upsert: the in-progress field map + an optional filter predicate (status stays draft)."""
    record_type: str
    bindings: list[FieldBindingIn]
    filter_predicate: Optional[dict[str, Any]] = None


class DraftDefinitionResponse(CamelModel):
    record_type: str
    status: str
    version: int


class ActivateRequest(CamelModel):
    record_type: str


class ActivateResponse(CamelModel):
    record_type: str
    status: str
    version: int
    resolved_grains: list[str]


class ChainJobOut(CamelModel):
    """One job in a dataset's ingestion chain (sync → unpack → resolved → analytics)."""
    id: str
    job_type: str
    status: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DatasetScheduleOut(CamelModel):
    """The active recurring schedule bound to a dataset, if one exists."""
    id: str
    name: str
    cron: str
    enabled: bool
    next_check_at: Optional[datetime] = None
    last_fire_at: Optional[datetime] = None


class DatasetJobsResponse(CamelModel):
    """The dataset's recent chain jobs (newest first) + its active schedule (the 'Job chain' panel)."""
    record_type: str
    jobs: list[ChainJobOut]
    schedule: Optional[DatasetScheduleOut] = None
