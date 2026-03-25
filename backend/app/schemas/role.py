"""Pydantic schemas for role CRUD API."""
from pydantic import Field
from app.schemas.base import CamelModel


class RoleCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    app_access: list[str] = Field(default_factory=list)  # App slugs — frontend sends as "appAccess"
    permissions: list[str] = Field(default_factory=list)  # Permission strings


class RoleUpdate(CamelModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    app_access: list[str] | None = None
    permissions: list[str] | None = None
