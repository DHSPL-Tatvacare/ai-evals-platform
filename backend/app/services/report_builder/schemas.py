"""Request/response schemas for the report builder API."""
from __future__ import annotations

from datetime import datetime

from app.schemas.base import CamelModel


class BuilderChatRequest(CamelModel):
    app_id: str
    session_id: str | None = None
    resume_from_seq: int | None = None
    message: str
    provider: str
    model: str


class BuilderSectionOut(CamelModel):
    id: str
    type: str
    title: str
    variant: str = ""


class ComposedReportOut(CamelModel):
    report_name: str
    sections: list[BuilderSectionOut]


class ToolCallDetailOut(CamelModel):
    execution_ms: float
    sql_used: str | None = None
    row_count: int | None = None
    cache_hit: bool | None = None
    error: str | None = None


class ToolCallOut(CamelModel):
    tool_call_id: str | None = None
    name: str
    summary: str
    detail: ToolCallDetailOut | None = None


class ChartSeriesItemOut(CamelModel):
    data_key: str
    type: str
    stack_id: str | None = None


class ChartSpecOut(CamelModel):
    type: str
    title: str
    x_key: str
    y_key: str | None = None
    series_keys: list[str] = []
    x_label: str = ""
    y_label: str = ""
    legend_position: str = "bottom"
    alternatives: list[str] = []
    series: list[ChartSeriesItemOut] = []


class ChartOut(CamelModel):
    spec: ChartSpecOut
    data: list[dict] = []
    sql_query: str = ""
    source_question: str = ""


class BuilderChatResponse(CamelModel):
    session_id: str
    provider: str | None = None
    model: str | None = None
    role: str = "assistant"
    content: str
    terminal_status: str | None = None
    tool_calls: list[ToolCallOut] = []
    composed_report: ComposedReportOut | None = None
    chart: ChartOut | None = None
    warnings: list[str] = []


class BuilderSessionResponse(CamelModel):
    session_id: str
    provider: str
    model: str


class BuilderMessageOut(CamelModel):
    id: str
    role: str
    content: str
    status: str
    error_message: str | None = None
    metadata: dict | None = None
    created_at: datetime


class BuilderSessionSnapshotResponse(CamelModel):
    session_id: str
    provider: str
    model: str
    last_event_seq: int
    current_turn_status: str
    messages: list[BuilderMessageOut] = []


class BuilderRuntimeEventOut(CamelModel):
    seq: int
    event_type: str
    payload: dict
    created_at: datetime


class BuilderRuntimeEventsResponse(CamelModel):
    session_id: str
    last_event_seq: int
    events: list[BuilderRuntimeEventOut] = []
