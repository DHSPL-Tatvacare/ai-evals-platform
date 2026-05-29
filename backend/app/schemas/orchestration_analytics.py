"""Response schemas for the orchestration analytics surface (camelCase JSON)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from app.schemas.base import CamelModel


class OverviewResponse(CamelModel):
    campaigns: int
    runs: int
    recipients: int
    unique_contacts: int
    positive: int
    reached: int
    no_response: int
    failed: int
    in_flight: int
    spend: float
    in_flight_runs: int
    cohort_total: int


class BreakdownRowResponse(CamelModel):
    key: str
    label: str
    provider: Optional[str] = None
    recipients: int
    dispatched: int
    positive: int
    reached: int
    no_response: int
    failed: int
    in_flight: int
    avg_cost: float
    cost: float


class BreakdownResponse(CamelModel):
    dimension: str
    rows: list[BreakdownRowResponse]


class RunRowResponse(CamelModel):
    run_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    channel: Optional[str] = None
    triggered_by: str
    status: str
    cohort_size: int
    reached: int
    positive: int
    cost: float
    started_at: Optional[datetime] = None


class RunsResponse(CamelModel):
    rows: list[RunRowResponse]
    total: int
    page: int
    page_size: int


class RunBucketsResponse(CamelModel):
    positive: int
    reached: int
    no_response: int
    failed: int
    in_flight: int


class RunNodeStepResponse(CamelModel):
    node_step_id: uuid.UUID
    node_id: str
    node_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunActionResponse(CamelModel):
    action_id: uuid.UUID
    recipient_id: str
    channel: str
    action_type: str
    status: str
    outcome_bucket: Optional[str] = None
    contact: Optional[str] = None
    cost: Optional[float] = None
    created_at: Optional[datetime] = None


class RunDetailResponse(CamelModel):
    run_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    status: str
    triggered_by: str
    cohort_size: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    buckets: RunBucketsResponse
    spend: float
    node_steps: list[RunNodeStepResponse]
    actions: list[RunActionResponse]
    actions_total: int


class TrendPointResponse(CamelModel):
    date: datetime
    positive: int
    reached: int
    no_response: int
    failed: int


class TrendResponse(CamelModel):
    points: list[TrendPointResponse]


class SignalResponse(CamelModel):
    severity: str
    title: str
    detail: str
    metric: Optional[dict[str, Any]] = None


class SignalsResponse(CamelModel):
    signals: list[SignalResponse]
    generated_at: Optional[datetime] = None


class RunReportFunnelStage(CamelModel):
    key: str
    label: str
    count: int


class RunReportChannel(CamelModel):
    capability: str
    vendor: Optional[str] = None
    connection_label: Optional[str] = None
    stages: list[RunReportFunnelStage]
    metrics: dict[str, Any]


class RunReportRecipientChannel(CamelModel):
    capability: str
    outcome_bucket: Optional[str] = None
    stage_reached: Optional[str] = None
    summary: Optional[str] = None
    metrics: dict[str, Any]


class RunReportRecipient(CamelModel):
    recipient_id: str
    display_name: Optional[str] = None
    contact_last4: Optional[str] = None
    attributes: dict[str, Any]
    channels: list[RunReportRecipientChannel]


class RunReportResponse(CamelModel):
    run_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    app_id: str
    status: str
    triggered_by: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    recipients_total: int
    spend: float
    buckets: RunBucketsResponse
    channels: list[RunReportChannel]
    recipients: list[RunReportRecipient]
    recipients_total_count: int
