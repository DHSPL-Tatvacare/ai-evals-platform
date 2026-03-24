"""Schemas for Inside Sales API."""

from typing import Optional

from pydantic import Field

from app.schemas.base import CamelModel


class CallRecord(CamelModel):
    activity_id: str
    prospect_id: str
    agent_name: str
    agent_email: str
    event_code: int
    direction: str
    status: str
    call_start_time: str
    duration_seconds: int
    recording_url: str
    phone_number: str
    display_number: str
    call_notes: str
    call_session_id: str
    created_on: str
    lead_name: str


class CallListResponse(CamelModel):
    calls: list[CallRecord]
    total: int
    page: int
    page_size: int


class CallListParams(CamelModel):
    date_from: str = Field(..., description="Start date YYYY-MM-DD HH:MM:SS")
    date_to: str = Field(..., description="End date YYYY-MM-DD HH:MM:SS")
    page: int = 1
    page_size: int = 50
    agent: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    event_codes: Optional[str] = None  # Comma-separated
