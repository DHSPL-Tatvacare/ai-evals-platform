"""Canonical print document contract for Playwright export."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.base import CamelModel


class PrintThemeTokenSet(CamelModel):
    accent: str
    accent_muted: str
    border: str
    text_primary: str
    text_secondary: str
    background: str


class DocumentBlockBase(CamelModel):
    id: str
    title: str | None = None


class CoverBlock(DocumentBlockBase):
    type: Literal["cover"] = "cover"
    subtitle: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class StatGridItem(CamelModel):
    label: str
    value: str
    tone: str = "neutral"


class StatGridBlock(DocumentBlockBase):
    type: Literal["stat_grid"] = "stat_grid"
    items: list[StatGridItem]


class ProseBlock(DocumentBlockBase):
    type: Literal["prose"] = "prose"
    body: str


class TableColumn(CamelModel):
    key: str
    label: str
    align: Literal["left", "center", "right"] = "left"


class TableBlock(DocumentBlockBase):
    type: Literal["table"] = "table"
    columns: list[TableColumn]
    rows: list[dict[str, str | int | float | None]]


class HeatmapCell(CamelModel):
    label: str
    value: float | None = None
    tone: str = "neutral"


class HeatmapTableRow(CamelModel):
    label: str
    cells: list[HeatmapCell]


class HeatmapTableBlock(DocumentBlockBase):
    type: Literal["heatmap_table"] = "heatmap_table"
    columns: list[str]
    rows: list[HeatmapTableRow]


class MetricBarItem(CamelModel):
    label: str
    value: float
    max_value: float = 100
    tone: str = "neutral"


class MetricBarListBlock(DocumentBlockBase):
    type: Literal["metric_bar_list"] = "metric_bar_list"
    items: list[MetricBarItem]


class RecommendationListItem(CamelModel):
    priority: str
    title: str
    summary: str


class RecommendationListBlock(DocumentBlockBase):
    type: Literal["recommendation_list"] = "recommendation_list"
    items: list[RecommendationListItem]


class EntityTableBlock(DocumentBlockBase):
    type: Literal["entity_table"] = "entity_table"
    columns: list[TableColumn]
    rows: list[dict[str, str | int | float | None]]


class PageBreakBlock(DocumentBlockBase):
    type: Literal["page_break"] = "page_break"


PlatformDocumentBlock = Annotated[
    CoverBlock
    | StatGridBlock
    | ProseBlock
    | TableBlock
    | HeatmapTableBlock
    | MetricBarListBlock
    | RecommendationListBlock
    | EntityTableBlock
    | PageBreakBlock,
    Field(discriminator="type"),
]


class PlatformReportDocument(CamelModel):
    schema_version: Literal["v1"] = "v1"
    title: str
    subtitle: str | None = None
    theme: PrintThemeTokenSet
    blocks: list[PlatformDocumentBlock]
