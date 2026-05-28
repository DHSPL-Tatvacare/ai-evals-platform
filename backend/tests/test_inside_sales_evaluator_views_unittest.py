"""Multi-evaluator runs surface one EvaluatorReportView per evaluator.

A single-evaluator run keeps the flat top-level sections and leaves
evaluator_views=None. A 2-evaluator run keeps the primary evaluator as the
flat top-level view (back-compat) AND emits one EvaluatorReportView per
evaluator, each carrying that evaluator's own sections. Dimension card tone
keys off each dimension's own thresholds, not the /100 rate band.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from app.schemas.app_analytics_config import (
    AnalyticsCompositionConfig,
    AnalyticsSectionConfig,
    AppAnalyticsConfig,
)
from app.services.reports.canonical_adapters import adapt_inside_sales_run_report
from app.services.reports.contracts.report_sections import MetricBreakdownSection
from app.services.reports.contracts.run_report import PlatformRunReportPayload
from app.services.reports.inside_sales_schemas import InsideSalesReportPayload

FIXTURE = Path(__file__).parent / "fixtures" / "reports" / "inside-sales-run.json"


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())


def _config() -> AppAnalyticsConfig:
    return AppAnalyticsConfig(
        single_run=AnalyticsCompositionConfig(
            sections=[
                AnalyticsSectionConfig(
                    id="inside-sales-summary",
                    type="summary_cards",
                    title="Summary",
                ),
                AnalyticsSectionConfig(
                    id="inside-sales-dimensions",
                    type="metric_breakdown",
                    title="Dimensions",
                ),
            ],
        ),
    )


def _single_evaluator_aggregate(raw: dict) -> dict:
    return {
        "id": "ev-1",
        "name": "Evaluator One",
        "runSummary": raw["runSummary"],
        "dimensionBreakdown": raw["dimensionBreakdown"],
        "complianceBreakdown": raw["complianceBreakdown"],
        "flagStats": raw["flagStats"],
        "agentSlices": raw["agentSlices"],
    }


def _two_evaluator_payload() -> InsideSalesReportPayload:
    raw = _raw()
    first = _single_evaluator_aggregate(raw)

    second = copy.deepcopy(first)
    second["id"] = "ev-2"
    second["name"] = "Evaluator Two"
    # Diverge the second evaluator so its sections must differ from the first.
    second["runSummary"]["avgQaScore"] = 42
    second["dimensionBreakdown"]["discovery"]["avg"] = 30

    raw["perEvaluator"] = {"ev-1": first, "ev-2": second}
    return InsideSalesReportPayload.model_validate(raw)


def _single_evaluator_payload() -> InsideSalesReportPayload:
    raw = _raw()
    raw["perEvaluator"] = {"ev-1": _single_evaluator_aggregate(raw)}
    return InsideSalesReportPayload.model_validate(raw)


def test_two_evaluator_run_emits_one_view_per_evaluator():
    report = adapt_inside_sales_run_report(_two_evaluator_payload(), _config())
    assert report.evaluator_views is not None
    assert [v.evaluator_id for v in report.evaluator_views] == ["ev-1", "ev-2"]
    assert [v.evaluator_name for v in report.evaluator_views] == [
        "Evaluator One",
        "Evaluator Two",
    ]


def test_evaluator_views_differ_where_aggregates_differ():
    report = adapt_inside_sales_run_report(_two_evaluator_payload(), _config())
    assert report.evaluator_views is not None
    view_one, view_two = report.evaluator_views

    def _dim_value(view):
        section = next(s for s in view.sections if s.id == "inside-sales-dimensions")
        assert isinstance(section, MetricBreakdownSection)
        return section.data[0].value

    assert _dim_value(view_one) == 79
    assert _dim_value(view_two) == 30


def test_single_evaluator_run_yields_no_views():
    report = adapt_inside_sales_run_report(_single_evaluator_payload(), _config())
    assert report.evaluator_views is None


def test_top_level_sections_equal_primary_evaluator():
    report = adapt_inside_sales_run_report(_two_evaluator_payload(), _config())
    assert report.evaluator_views is not None
    primary = report.evaluator_views[0]
    assert [s.id for s in report.sections] == [s.id for s in primary.sections]
    top_dim = next(s for s in report.sections if s.id == "inside-sales-dimensions")
    view_dim = next(s for s in primary.sections if s.id == "inside-sales-dimensions")
    assert isinstance(top_dim, MetricBreakdownSection)
    assert isinstance(view_dim, MetricBreakdownSection)
    assert top_dim.data[0].value == view_dim.data[0].value == 79


def test_dimension_card_tone_uses_dimension_scale_not_rate_band():
    # Discovery avg 79 on a /100 dimension with green=80, yellow=60.
    # Under _rate_tone (>=85 positive, >=60 warning) 79 -> warning anyway, so
    # construct a mixed-scale dimension where the two scales disagree: a mean of
    # 4.84 on a max-10 dimension clears its 4.0 green threshold (positive) but
    # would be "negative" under the /100 _rate_tone band.
    raw = _raw()
    raw["dimensionBreakdown"] = {
        "rapport": {
            "label": "Rapport",
            "avg": 4.84,
            "min": 1.0,
            "max": 9.0,
            "maxPossible": 10,
            "greenThreshold": 4.0,
            "yellowThreshold": 2.0,
            "distribution": [2, 3, 5, 6, 2],
        }
    }
    payload = InsideSalesReportPayload.model_validate(raw)
    report = adapt_inside_sales_run_report(payload, _config())
    section = next(s for s in report.sections if s.id == "inside-sales-dimensions")
    assert isinstance(section, MetricBreakdownSection)
    card = section.data[0]
    assert card.value == 4.84
    assert card.tone == "positive"


def test_existing_single_evaluator_payload_round_trips_without_views_key():
    # Existing cached artifacts have no evaluator_views key; they must still parse.
    raw = {
        "schemaVersion": "v1",
        "metadata": {
            "appId": "inside-sales",
            "runId": "run-1",
            "evalType": "call_quality",
            "createdAt": "2026-04-01T09:00:00+00:00",
            "computedAt": "2026-04-01T10:00:00+00:00",
        },
        "sections": [],
        "exportDocument": {
            "title": "x",
            "subtitle": None,
            "theme": {
                "accent": "#000",
                "accentMuted": "#111",
                "border": "#222",
                "textPrimary": "#333",
                "textSecondary": "#444",
                "background": "#fff",
            },
            "blocks": [],
        },
    }
    parsed = PlatformRunReportPayload.model_validate(raw)
    assert parsed.evaluator_views is None
