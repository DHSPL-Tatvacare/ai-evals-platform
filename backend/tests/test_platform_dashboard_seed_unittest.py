"""Cross-run report is cataloged as a platform dashboard entry (`is_platform`).

Platform dashboards are SYSTEM-owned + shared, so the existing
`readable_scope_clause` already surfaces them to every tenant; `is_platform`
is the explicit marker the library list badges and pins on.
"""
from __future__ import annotations

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.analytics_dashboard import AnalyticsDashboard
from app.models.mixins.shareable import Visibility
from app.routes.analytics_library import _dashboard_to_dict
from app.services.seed_defaults import _build_platform_dashboard_seeds


def test_dashboard_dict_exposes_is_platform():
    dashboard = AnalyticsDashboard(
        app_id="inside-sales", title="Cross-Run Report", is_platform=True
    )
    assert _dashboard_to_dict(dashboard)["isPlatform"] is True


def test_cross_run_dashboard_seeded_as_platform_entry():
    by_app = {s["app_id"]: s for s in _build_platform_dashboard_seeds()}
    # inside-sales ships cross-run sections, so it gets the platform entry.
    assert "inside-sales" in by_app
    seed = by_app["inside-sales"]
    assert seed["is_platform"] is True
    assert seed["tenant_id"] == SYSTEM_TENANT_ID
    assert seed["user_id"] == SYSTEM_USER_ID
    assert seed["visibility"] == Visibility.SHARED


def test_platform_dashboard_seed_ids_are_stable():
    first = {s["app_id"]: s["id"] for s in _build_platform_dashboard_seeds()}
    second = {s["app_id"]: s["id"] for s in _build_platform_dashboard_seeds()}
    assert first == second
