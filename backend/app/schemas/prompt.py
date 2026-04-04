"""Prompt request/response schemas."""

import uuid
from datetime import datetime
from typing import Optional

from app.models.mixins.shareable import Visibility
from app.schemas.base import CamelModel, CamelORMModel
from app.schemas.visibility import VisibilityInputMixin, VisibilityOutputMixin


class PromptCreate(VisibilityInputMixin, CamelModel):
    app_id: str
    prompt_type: str
    branch_key: Optional[str] = None
    name: str
    prompt: str
    description: str = ""
    is_default: bool = False
    source_type: Optional[str] = None
    visibility: Visibility = Visibility.PRIVATE
    forked_from: Optional[int] = None


class PromptUpdate(CamelModel):
    name: Optional[str] = None
    prompt: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    source_type: Optional[str] = None

    def requires_new_version(self) -> bool:
        return any(
            getattr(self, field) is not None
            for field in ("prompt", "source_type", "is_default")
        )


class PromptResponse(VisibilityOutputMixin, CamelORMModel):
    id: int
    app_id: str
    prompt_type: str
    branch_key: str
    version: int
    name: str
    prompt: str
    description: str
    is_default: bool
    source_type: Optional[str] = None
    visibility: Visibility
    forked_from: Optional[int] = None
    shared_by: Optional[uuid.UUID] = None
    shared_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    tenant_id: uuid.UUID
    user_id: uuid.UUID
