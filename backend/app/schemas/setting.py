"""Setting request/response schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.models.mixins.shareable import Visibility
from app.schemas.base import CamelModel, CamelORMModel
from app.schemas.visibility import VisibilityInputMixin, VisibilityOutputMixin


class SettingCreate(VisibilityInputMixin, CamelModel):
    app_id: Optional[str] = None
    key: str
    value: dict = Field(default_factory=dict)
    visibility: Visibility = Visibility.PRIVATE
    forked_from: Optional[int] = None


class SettingUpdate(VisibilityInputMixin, CamelModel):
    value: Optional[dict] = None
    visibility: Optional[Visibility] = None
    forked_from: Optional[int] = None


class SettingResponse(VisibilityOutputMixin, CamelORMModel):
    id: int
    app_id: Optional[str] = None
    key: str
    value: dict
    visibility: Visibility
    forked_from: Optional[int] = None
    updated_by: Optional[uuid.UUID] = None
    shared_by: Optional[uuid.UUID] = None
    shared_at: Optional[datetime] = None
    updated_at: datetime
    tenant_id: uuid.UUID
    user_id: uuid.UUID
