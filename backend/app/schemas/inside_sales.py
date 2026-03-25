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
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    cached: bool = False


class LeadListRecord(CamelModel):
    prospect_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    prospect_stage: str
    city: Optional[str] = None
    age_group: Optional[str] = None
    condition: Optional[str] = None
    hba1c_band: Optional[str] = None
    intent_to_pay: Optional[str] = None
    agent_name: Optional[str] = None
    rnr_count: int = 0
    answered_count: int = 0
    total_dials: int = 0
    connect_rate: Optional[float] = None      # None when total_dials == 0
    frt_seconds: Optional[int] = None         # None when null source or negative delta
    lead_age_days: int = 0
    days_since_last_contact: Optional[int] = None  # None when no activity yet
    mql_score: int = 0
    mql_signals: dict[str, bool] = Field(default_factory=dict)
    created_on: str
    last_activity_on: Optional[str] = None
    source: Optional[str] = None
    source_campaign: Optional[str] = None


class LeadListResponse(CamelModel):
    leads: list[LeadListRecord]
    total: int
    page: int
    page_size: int


class LeadCallRecord(CamelModel):
    activity_id: str
    call_time: str
    agent_name: Optional[str] = None
    duration_seconds: int = 0
    status: str
    recording_url: Optional[str] = None
    eval_score: Optional[float] = None
    is_counseling: bool = False              # duration_seconds >= 600


class LeadDetailFullResponse(CamelModel):
    # Profile
    prospect_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    prospect_stage: str
    city: Optional[str] = None
    age_group: Optional[str] = None
    condition: Optional[str] = None
    hba1c_band: Optional[str] = None
    blood_sugar_band: Optional[str] = None
    diabetes_duration: Optional[str] = None
    current_management: Optional[str] = None
    goal: Optional[str] = None
    intent_to_pay: Optional[str] = None
    job_title: Optional[str] = None
    preferred_call_time: Optional[str] = None
    agent_name: Optional[str] = None
    source: Optional[str] = None
    source_campaign: Optional[str] = None
    created_on: str
    # MQL
    mql_score: int = 0
    mql_signals: dict[str, bool] = Field(default_factory=dict)
    # Computed metrics
    frt_seconds: Optional[int] = None
    total_dials: int = 0
    connect_rate: Optional[float] = None
    counseling_count: int = 0
    counseling_rate: Optional[float] = None
    callback_adherence_seconds: Optional[int] = None
    lead_age_days: int = 0
    days_since_last_contact: Optional[int] = None
    # Call history
    call_history: list[LeadCallRecord] = Field(default_factory=list)
    history_truncated: bool = False
    # Eval history — reuses existing ThreadEvalRow shape, typed as list for flexibility
    eval_history: list[dict] = Field(default_factory=list)
