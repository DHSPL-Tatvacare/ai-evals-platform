"""Cross-run layout-group defaults (Bug 1).

The cross-run Summary tab must be curated by backend layout groups, mirroring
the single-run scheme: summary tab = the AI narrative (the cross-run synthesis),
detailed tab = every section. Before this, cross-run shipped empty layoutGroups
and the frontend fell back to a single-run filter, collapsing Summary to one
block.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

svc = importlib.import_module("app.services.reports.report_generation_service")


def _cfg(section_id: str, component_id: str):
    # _default_cross_run_layout_groups only reads .section_id / .component_id.
    return SimpleNamespace(section_id=section_id, component_id=component_id)


def test_cross_run_summary_group_is_narrative_only():
    cfgs = [
        _cfg("x-summary", "summary_cards"),
        _cfg("x-narrative", "narrative"),
        _cfg("x-trend", "trend_chart"),
        _cfg("x-insights", "insight_panels"),
    ]
    groups = svc._default_cross_run_layout_groups(cfgs)
    by_tab = {g["tab"]: g for g in groups}
    assert by_tab["summary"]["sectionIds"] == ["x-narrative"]
    assert by_tab["detailed"]["sectionIds"] == [
        "x-summary", "x-narrative", "x-trend", "x-insights",
    ]


def test_cross_run_layout_groups_empty_when_no_sections():
    assert svc._default_cross_run_layout_groups([]) == []


def test_cross_run_summary_omitted_when_no_narrative_section():
    cfgs = [_cfg("x-summary", "summary_cards"), _cfg("x-trend", "trend_chart")]
    groups = svc._default_cross_run_layout_groups(cfgs)
    by_tab = {g["tab"]: g for g in groups}
    assert "summary" not in by_tab
    assert by_tab["detailed"]["sectionIds"] == ["x-summary", "x-trend"]


def test_cross_run_scope_spec_uses_cross_run_builder():
    assert svc.CROSS_RUN_SCOPE_SPEC.layout_groups_builder is svc._default_cross_run_layout_groups
    assert svc.SINGLE_RUN_SCOPE_SPEC.layout_groups_builder is svc._default_single_run_layout_groups
