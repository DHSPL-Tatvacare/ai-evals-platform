"""Schemas for published rule catalogs."""

from pydantic import ConfigDict, Field

from app.schemas.base import CamelModel


class RuleCatalogEntry(CamelModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    rule_text: str
    section: str = ""
    tags: list[str] = Field(default_factory=list)
    goal_ids: list[str] = Field(default_factory=list)
    evaluation_scopes: list[str] = Field(default_factory=list)


class RuleCatalogResponse(CamelModel):
    rules: list[RuleCatalogEntry] = Field(default_factory=list)
