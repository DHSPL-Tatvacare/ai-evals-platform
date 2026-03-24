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
    last_eval_score: Optional[float] = None
    eval_count: int = 0


class CallListResponse(CamelModel):
    calls: list[CallRecord]
    total: int
    page: int
    page_size: int


class AgentListResponse(CamelModel):
    agents: list[str]


class LeadDetailResponse(CamelModel):
    prospect_id: str
    first_name: str
    last_name: str
    phone: str
    email: str
    cached: bool = False
