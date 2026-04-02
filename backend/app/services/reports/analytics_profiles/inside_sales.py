"""Inside Sales reporting analytics profile."""

from __future__ import annotations

from app.services.reports.analytics_profiles.base import AnalyticsProfile, CrossRunAdapter
from app.services.reports.cross_run_aggregator import CrossRunAISummary
from app.services.reports.cross_run_narrator import CrossRunNarrator
from app.services.reports.inside_sales_cross_run import (
    InsideSalesCrossRunAggregator,
    InsideSalesCrossRunAnalytics,
)
from app.services.reports.inside_sales_pdf_template import render_inside_sales_report_html
from app.services.reports.inside_sales_report_service import InsideSalesReportService
from app.services.reports.inside_sales_schemas import InsideSalesReportPayload


class InsideSalesCrossRunAdapter(CrossRunAdapter):
    analytics_model = InsideSalesCrossRunAnalytics

    def aggregate(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
    ) -> InsideSalesCrossRunAnalytics:
        return InsideSalesCrossRunAggregator(runs_data, all_runs_count).aggregate()


INSIDE_SALES_ANALYTICS_PROFILE = AnalyticsProfile(
    key="inside_sales_v1",
    report_service_cls=InsideSalesReportService,
    report_payload_model=InsideSalesReportPayload,
    pdf_renderer=render_inside_sales_report_html,
    cross_run_adapter=InsideSalesCrossRunAdapter(),
    cross_run_summary_narrator_cls=CrossRunNarrator,
    cross_run_summary_model=CrossRunAISummary,
)
