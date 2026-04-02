"""Canonical cross-run report contract."""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel
from app.services.reports.contracts.print_document import PlatformReportDocument
from app.services.reports.contracts.report_sections import PlatformReportSection


class PlatformCrossRunMetadata(CamelModel):
    app_id: str
    report_kind: Literal["cross_run"] = "cross_run"
    computed_at: str
    source_run_count: int
    total_runs_available: int
    cache_key: str | None = None


class PlatformCrossRunPayload(CamelModel):
    schema_version: Literal["v1"] = "v1"
    metadata: PlatformCrossRunMetadata
    sections: list[PlatformReportSection]
    export_document: PlatformReportDocument | None = None
