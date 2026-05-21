"""Cross-run heatmap rows must carry the contract-required `key`.

`HeatmapRow.key` is non-optional, so any cross-run adapter that emits heatmap
rows without a key raises ValidationError when the section is composed. This
drives the live inside-sales cross-run path (`adapt_inside_sales_cross_run_from_runs`)
end-to-end and asserts every heatmap row is keyed.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.schemas.app_analytics_config import (
    AnalyticsCompositionConfig,
    AnalyticsSectionConfig,
    AppAnalyticsConfig,
)
from app.services.reports.canonical_adapters import (
    adapt_inside_sales_cross_run_from_runs,
    adapt_inside_sales_run_report,
)
from app.services.reports.contracts.report_sections import HeatmapSection
from app.services.reports.inside_sales_schemas import InsideSalesReportPayload

FIXTURE = Path(__file__).parent / "fixtures" / "reports" / "inside-sales-run.json"


def _single_run_config() -> AppAnalyticsConfig:
    return AppAnalyticsConfig(
        single_run=AnalyticsCompositionConfig(
            sections=[
                AnalyticsSectionConfig(id="inside-sales-summary", type="summary_cards"),
                AnalyticsSectionConfig(id="inside-sales-dimensions", type="metric_breakdown"),
                AnalyticsSectionConfig(id="inside-sales-compliance", type="compliance_table"),
            ],
        ),
    )


def _cross_run_config() -> AppAnalyticsConfig:
    return AppAnalyticsConfig(
        cross_run=AnalyticsCompositionConfig(
            sections=[
                AnalyticsSectionConfig(id="inside-sales-cross-dimensions", type="heatmap"),
                AnalyticsSectionConfig(id="inside-sales-cross-compliance", type="heatmap"),
            ],
        ),
    )


def _runs_data() -> list[tuple[dict, dict]]:
    payload = InsideSalesReportPayload.model_validate(json.loads(FIXTURE.read_text()))
    run_report = adapt_inside_sales_run_report(payload, _single_run_config())
    data = run_report.model_dump(by_alias=True)
    return [
        ({"id": "sales-1", "created_at": "2026-03-01T00:00:00+00:00"}, data),
        ({"id": "sales-2", "created_at": "2026-03-02T00:00:00+00:00"}, data),
    ]


def test_inside_sales_cross_run_heatmap_rows_are_keyed():
    report = adapt_inside_sales_cross_run_from_runs(
        _runs_data(), _cross_run_config(), app_id="inside-sales", total_runs_available=2
    )
    heatmaps = [s for s in report.sections if isinstance(s, HeatmapSection)]
    assert {s.id for s in heatmaps} == {
        "inside-sales-cross-dimensions",
        "inside-sales-cross-compliance",
    }
    for section in heatmaps:
        assert section.data.rows, f"{section.id} produced no rows to key-check"
        for row in section.data.rows:
            assert row.key, f"{section.id} row missing key"
