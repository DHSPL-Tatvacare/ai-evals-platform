"""Kaira reporting analytics profile."""

from __future__ import annotations

from app.services.reports.analytics_profiles.base import AnalyticsProfile, CrossRunAdapter
from app.services.reports.cross_run_aggregator import (
    CrossRunAISummary,
    CrossRunAggregator,
    CrossRunAnalytics,
)
from app.services.reports.cross_run_narrator import CrossRunNarrator
from app.services.reports.pdf_template import render_report_html
from app.services.reports.report_service import ReportService
from app.services.reports.schemas import ReportPayload


class KairaCrossRunAdapter(CrossRunAdapter):
    analytics_model = CrossRunAnalytics

    def aggregate(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
    ) -> CrossRunAnalytics:
        return CrossRunAggregator(runs_data, all_runs_count).aggregate()


KAIRA_ANALYTICS_PROFILE = AnalyticsProfile(
    key="kaira_v1",
    report_service_cls=ReportService,
    report_payload_model=ReportPayload,
    pdf_renderer=render_report_html,
    cross_run_adapter=KairaCrossRunAdapter(),
    cross_run_summary_narrator_cls=CrossRunNarrator,
    cross_run_summary_model=CrossRunAISummary,
)
