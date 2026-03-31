"""Code-first analytics registry for app-specific report capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.schemas.base import CamelModel
from app.services.reports.cross_run_aggregator import (
    CrossRunAggregator,
    CrossRunAISummary,
    CrossRunAnalytics,
)
from app.services.reports.cross_run_narrator import CrossRunNarrator
from app.services.reports.inside_sales_cross_run import (
    InsideSalesCrossRunAggregator,
    InsideSalesCrossRunAnalytics,
)
from app.services.reports.inside_sales_pdf_template import (
    render_inside_sales_report_html,
)
from app.services.reports.inside_sales_report_service import (
    InsideSalesReportService,
)
from app.services.reports.inside_sales_schemas import InsideSalesReportPayload
from app.services.reports.pdf_template import render_report_html
from app.services.reports.report_service import ReportService
from app.services.reports.schemas import ReportPayload


class CrossRunAdapter:
    analytics_model: type[CamelModel]

    def aggregate(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
    ) -> CamelModel:
        raise NotImplementedError

    def load_cached(self, payload: dict) -> CamelModel:
        return self.analytics_model.model_validate(payload)


class KairaCrossRunAdapter(CrossRunAdapter):
    analytics_model = CrossRunAnalytics

    def aggregate(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
    ) -> CrossRunAnalytics:
        return CrossRunAggregator(runs_data, all_runs_count).aggregate()


class InsideSalesCrossRunAdapter(CrossRunAdapter):
    analytics_model = InsideSalesCrossRunAnalytics

    def aggregate(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
    ) -> InsideSalesCrossRunAnalytics:
        return InsideSalesCrossRunAggregator(runs_data, all_runs_count).aggregate()


@dataclass(frozen=True)
class AnalyticsCapabilities:
    single_run_report: bool = True
    cross_run_analytics: bool = False
    pdf_export: bool = False
    cross_run_ai_summary: bool = False


@dataclass(frozen=True)
class AnalyticsAppConfig:
    app_id: str
    report_service_cls: type
    report_payload_model: type[CamelModel]
    pdf_renderer: Callable[[dict], str] | None
    cross_run_adapter: CrossRunAdapter | None
    cross_run_summary_narrator_cls: type | None
    cross_run_summary_model: type[CamelModel] | None
    capabilities: AnalyticsCapabilities


_REGISTRY: dict[str, AnalyticsAppConfig] = {
    "kaira-bot": AnalyticsAppConfig(
        app_id="kaira-bot",
        report_service_cls=ReportService,
        report_payload_model=ReportPayload,
        pdf_renderer=render_report_html,
        cross_run_adapter=KairaCrossRunAdapter(),
        cross_run_summary_narrator_cls=CrossRunNarrator,
        cross_run_summary_model=CrossRunAISummary,
        capabilities=AnalyticsCapabilities(
            single_run_report=True,
            cross_run_analytics=True,
            pdf_export=True,
            cross_run_ai_summary=True,
        ),
    ),
    "inside-sales": AnalyticsAppConfig(
        app_id="inside-sales",
        report_service_cls=InsideSalesReportService,
        report_payload_model=InsideSalesReportPayload,
        pdf_renderer=render_inside_sales_report_html,
        cross_run_adapter=InsideSalesCrossRunAdapter(),
        cross_run_summary_narrator_cls=CrossRunNarrator,
        cross_run_summary_model=CrossRunAISummary,
        capabilities=AnalyticsCapabilities(
            single_run_report=True,
            cross_run_analytics=True,
            pdf_export=True,
            cross_run_ai_summary=True,
        ),
    ),
}


def get_analytics_app_config(app_id: str) -> AnalyticsAppConfig | None:
    return _REGISTRY.get(app_id)
