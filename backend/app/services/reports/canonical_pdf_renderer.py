"""Helpers for rendering canonical payload export documents."""

from __future__ import annotations

from app.services.reports.contracts.run_report import PlatformRunReportPayload
from app.services.reports.html_renderer import render_report_document


def render_platform_report_html(payload_dict: dict) -> str:
    payload = PlatformRunReportPayload.model_validate(payload_dict)
    return render_report_document(payload.export_document)
