"""Agent Performance renders as an agents×skills heatmap, not entity-slice cards.

Columns lead with Avg QA, then one column per scored dimension. Each cell's tone
comes from that dimension's green/yellow thresholds (Avg QA from the 0–100 band),
so the grid reads as a coaching heatmap.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.schemas.app_analytics_config import (
    AnalyticsCompositionConfig,
    AnalyticsSectionConfig,
    AppAnalyticsConfig,
)
from app.services.reports.canonical_adapters import adapt_inside_sales_run_report
from app.services.reports.contracts.report_sections import HeatmapSection
from app.services.reports.inside_sales_schemas import InsideSalesReportPayload

FIXTURE = Path(__file__).parent / "fixtures" / "reports" / "inside-sales-run.json"


def _payload() -> InsideSalesReportPayload:
    return InsideSalesReportPayload.model_validate(json.loads(FIXTURE.read_text()))


def _agents_section(payload: InsideSalesReportPayload, config) -> HeatmapSection:
    report = adapt_inside_sales_run_report(payload, config)
    agents = next(s for s in report.sections if s.id == "inside-sales-agents")
    assert isinstance(agents, HeatmapSection)
    return agents


def _config() -> AppAnalyticsConfig:
    return AppAnalyticsConfig(
        single_run=AnalyticsCompositionConfig(
            sections=[
                AnalyticsSectionConfig(
                    id="inside-sales-agents",
                    type="heatmap",
                    title="Agent Performance",
                    variant="agent_performance",
                ),
            ],
        ),
    )


def test_agents_section_is_a_heatmap():
    agents = _agents_section(_payload(), _config())
    assert agents.type == "heatmap"


def test_agents_heatmap_columns_lead_with_avg_qa_then_dimensions():
    agents = _agents_section(_payload(), _config())
    assert agents.data.columns == ["Avg QA", "Discovery"]


def test_agents_heatmap_row_carries_scores_and_threshold_tones():
    agents = _agents_section(_payload(), _config())
    row = agents.data.rows[0]
    assert row.key == "agent-a"
    assert row.label == "Agent A"
    # Call count rides as the row sublabel (visible agent context in web + PDF),
    # not a cell tooltip that would vanish in the static export.
    assert row.sublabel == "8 calls"
    # Avg QA 84 sits below the 85 positive band → warning.
    assert row.cells[0].value == 84
    assert row.cells[0].tone == "warning"
    # Discovery 82 clears its 80 green threshold → positive.
    assert row.cells[1].value == 82
    assert row.cells[1].tone == "positive"
