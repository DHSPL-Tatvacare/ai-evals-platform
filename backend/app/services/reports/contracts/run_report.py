"""Canonical single-run report contract."""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel
from app.services.reports.contracts.print_document import PlatformReportDocument
from app.services.reports.contracts.report_sections import PlatformReportSection


class PlatformReportMetadata(CamelModel):
    app_id: str
    report_kind: Literal["single_run"] = "single_run"
    run_id: str
    run_name: str | None = None
    eval_type: str
    created_at: str
    computed_at: str
    source_run_count: int = 1
    llm_provider: str | None = None
    llm_model: str | None = None
    narrative_model: str | None = None
    cache_key: str | None = None


class PlatformRunReportPayload(CamelModel):
    schema_version: Literal["v1"] = "v1"
    metadata: PlatformReportMetadata
    sections: list[PlatformReportSection]
    export_document: PlatformReportDocument
