"""Listing request/response schemas."""
import uuid
from typing import Optional
from datetime import datetime
from pydantic import Field, field_validator
from app.schemas.base import CamelModel, CamelORMModel


class ListingCreate(CamelModel):
    app_id: str = Field(description="The app this listing belongs to.", examples=["support-assistant"])
    title: str = Field("", description="Human-readable label for the listing.", examples=["Call with Jane Cooper — 2026-05-20"])
    status: str = Field("draft", description="Lifecycle state: `draft` while being assembled, `ready` once it can be evaluated.", examples=["draft"])
    source_type: str = Field(
        "upload",
        description="Where the listing's data comes from — `upload` (attached files) or `api` (a captured API response). Fixed once set.",
        examples=["upload"],
    )
    audio_file: Optional[dict] = Field(None, description="Reference to an uploaded audio file: `{ \"id\", \"originalName\" }`.")
    transcript_file: Optional[dict] = Field(None, description="Reference to an uploaded transcript file.")
    structured_json_file: Optional[dict] = Field(None, description="Reference to an uploaded structured-JSON file.")
    transcript: Optional[dict] = Field(None, description="Inline transcript payload, when not provided as a file.")
    api_response: Optional[dict] = Field(None, description="Captured API response payload (only for `api` source type).")
    structured_output_references: list = Field([], description="Links to structured outputs produced elsewhere.")
    structured_outputs: list = Field([], description="Inline structured outputs attached to this listing.")


class ListingUpdate(CamelModel):
    title: Optional[str] = None
    status: Optional[str] = None
    source_type: Optional[str] = None
    audio_file: Optional[dict] = None
    transcript_file: Optional[dict] = None
    structured_json_file: Optional[dict] = None
    transcript: Optional[dict] = None
    api_response: Optional[dict] = None
    structured_output_references: Optional[list] = None
    structured_outputs: Optional[list] = None


class ListingResponse(CamelORMModel):
    id: uuid.UUID
    app_id: str
    title: str
    status: str
    source_type: str
    audio_file: Optional[dict] = None
    transcript_file: Optional[dict] = None
    structured_json_file: Optional[dict] = None
    transcript: Optional[dict] = None
    api_response: Optional[dict] = None
    structured_output_references: list = []
    structured_outputs: list = []
    created_at: datetime
    updated_at: datetime
    tenant_id: uuid.UUID
    user_id: uuid.UUID

    @field_validator(
        'structured_output_references', 'structured_outputs',
        mode='before'
    )
    @classmethod
    def none_to_list(cls, v):
        return v if v is not None else []
