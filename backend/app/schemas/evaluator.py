"""Evaluator request/response schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from app.models.mixins.shareable import Visibility
from app.schemas.base import CamelModel, CamelORMModel


class EvaluatorCreate(CamelModel):
    app_id: str
    listing_id: Optional[str] = None
    name: str
    prompt: str
    model_id: Optional[str] = None
    output_schema: list = Field(default_factory=list)
    visibility: Visibility = Visibility.PRIVATE
    linked_rule_ids: list[str] = Field(default_factory=list)
    forked_from: Optional[str] = None


class EvaluatorUpdate(CamelModel):
    listing_id: Optional[str] = None
    name: Optional[str] = None
    prompt: Optional[str] = None
    model_id: Optional[str] = None
    output_schema: Optional[list] = None
    visibility: Optional[Visibility] = None
    linked_rule_ids: Optional[list[str]] = None
    forked_from: Optional[str] = None


class EvaluatorSetGlobal(CamelModel):
    """Deprecated compatibility body for pre-harmonization clients."""

    is_global: bool


class EvaluatorSetBuiltIn(CamelModel):
    """Deprecated compatibility body for pre-harmonization clients."""

    is_built_in: bool


class EvaluatorResponse(CamelORMModel):
    id: uuid.UUID
    app_id: str
    listing_id: Optional[str] = None
    name: str
    prompt: str
    model_id: Optional[str] = None
    output_schema: list = Field(default_factory=list)
    visibility: Visibility
    linked_rule_ids: list[str] = Field(default_factory=list)
    shared_by: Optional[uuid.UUID] = None
    shared_at: Optional[datetime] = None
    # Transitional response-only fields. Remove after frontend harmonization.
    is_global: bool
    is_built_in: bool = False
    show_in_header: bool
    forked_from: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tenant_id: uuid.UUID
    user_id: uuid.UUID

    @field_validator('listing_id', 'forked_from', mode='before')
    @classmethod
    def uuid_to_str(cls, v):
        return str(v) if v is not None else None

    @field_validator('output_schema', mode='before')
    @classmethod
    def none_to_list(cls, v):
        return v if v is not None else []

    @field_validator('linked_rule_ids', mode='before')
    @classmethod
    def none_to_rule_ids(cls, v):
        return v if v is not None else []
