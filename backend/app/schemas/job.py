"""BackgroundJob request/response schemas."""
import uuid
from typing import Optional
from datetime import datetime
from pydantic import Field, model_validator
from app.schemas.base import CamelModel, CamelORMModel

# Keys stripped from job params in API responses to reduce payload size
_STRIPPED_PARAM_KEYS = {"csv_content"}


class JobCreate(CamelModel):
    job_type: str = Field(
        description="The registered operation to run. Determines which permission is required and which params are expected.",
        examples=["evaluate-batch"],
    )
    params: dict = Field(
        {},
        description="Job-type-specific inputs. Tenant, user, and app are injected automatically and need not be sent.",
        examples=[{"listingIds": ["7c9e6679-7425-40de-944b-e07fc1f90ae7"]}],
    )
    status: str = Field("queued", description="Initial status; normally left as the default `queued`.")
    progress: dict = Field(
        {"current": 0, "total": 0, "message": ""},
        description="Initial progress counter; the worker updates this as the job runs.",
    )
    # Generic submission-surface metadata round-tripped verbatim by callers
    # that need to correlate the job back to an originating session/turn.
    submission_context: Optional[dict] = Field(
        None,
        description="Optional caller metadata (e.g. originating session/turn) echoed back unchanged on the job.",
    )


class JobUpdate(CamelModel):
    status: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[dict] = None
    progress: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobResponse(CamelORMModel):
    id: uuid.UUID
    app_id: str
    job_type: str
    status: str
    priority: int
    queue_class: str
    attempt_count: int
    max_attempts: int
    params: dict
    submission_context: Optional[dict] = None
    result: Optional[dict] = None
    progress: dict
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None
    lease_expires_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    dead_lettered_at: Optional[datetime] = None
    dead_letter_reason: Optional[str] = None
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    queue_position: Optional[int] = None
    idempotency_key: Optional[str] = None

    @model_validator(mode="after")
    def strip_large_params(self):
        """Remove large payload keys (e.g. csv_content) from params to reduce response size."""
        if self.params:
            self.params = {k: v for k, v in self.params.items() if k not in _STRIPPED_PARAM_KEYS}
        return self
