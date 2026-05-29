"""Canonical cross-run report contract."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel
from app.services.reports.contracts.data_quality import DataQualityReport
from app.services.reports.contracts.print_document import PlatformReportDocument
from app.services.reports.contracts.report_sections import PlatformReportSection
from app.services.reports.contracts.run_report import (
    NarrativeStatus,
    PlatformReportPresentation,
)


class PlatformCrossRunMetadata(CamelModel):
    app_id: str
    report_kind: Literal["cross_run"] = "cross_run"
    computed_at: str
    source_run_count: int
    total_runs_available: int
    narrative_model: str | None = None
    narrative_status: NarrativeStatus | None = None
    narrative_error: str | None = None  # populated only when narrative_status='failed'
    cache_key: str | None = None


class PlatformCrossRunPayload(CamelModel):
    schema_version: Literal["v1"] = "v1"
    metadata: PlatformCrossRunMetadata
    # Defaulted so existing cached artifacts round-trip without requiring callers to pass it.
    presentation: PlatformReportPresentation = Field(default_factory=PlatformReportPresentation)
    sections: list[PlatformReportSection]
    export_document: PlatformReportDocument | None = None
    # Defaulted so existing cached cross-run artifacts round-trip without a
    # 409 on deploy. Now populated by the unified engine's finalize_data_quality
    # pass — cross-run previously shipped no data_quality at all.
    data_quality: DataQualityReport = Field(default_factory=DataQualityReport)
