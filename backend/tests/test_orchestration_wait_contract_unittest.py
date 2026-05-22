"""Phase 11 — logic.wait contract tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.node_registry import resolve_handler
from app.services.orchestration.nodes.logic_wait import expected_output_ids_for_config


def _wait_config(**kwargs):
    handler = resolve_handler(workflow_type="*", node_type="logic.wait")
    return handler.config_schema(**kwargs)


def test_legacy_duration_only_coerces_to_duration_mode():
    cfg = _wait_config(duration_hours=4)
    assert cfg.mode == "duration"
    assert cfg.duration_hours == 4


def test_legacy_until_datetime_only_coerces_to_until_mode():
    cfg = _wait_config(until_datetime=datetime(2026, 5, 1, 12, tzinfo=timezone.utc))
    assert cfg.mode == "until_datetime"


def test_explicit_duration_mode():
    cfg = _wait_config(mode="duration", duration_hours=2.5)
    assert cfg.mode == "duration"
    assert cfg.duration_hours == 2.5


def test_explicit_event_mode_requires_correlation():
    with pytest.raises(Exception):
        _wait_config(mode="event", event_name="lead_replied")
    cfg = _wait_config(
        mode="event",
        event_name="lead_replied",
        correlation={"recipient_id_field": "lead_id"},
    )
    assert cfg.mode == "event"


def test_event_or_timeout_requires_timeout_hours():
    with pytest.raises(Exception):
        _wait_config(
            mode="event_or_timeout",
            event_name="lead_replied",
            correlation={"recipient_id_field": "lead_id"},
        )
    cfg = _wait_config(
        mode="event_or_timeout",
        event_name="lead_replied",
        correlation={"recipient_id_field": "lead_id"},
        timeout_hours=24,
    )
    assert cfg.timeout_hours == 24


def test_no_mode_and_no_legacy_fields_raises():
    with pytest.raises(Exception):
        _wait_config()


def test_expected_output_ids_per_mode():
    assert expected_output_ids_for_config({"mode": "duration", "duration_hours": 4}) == ["wakeup"]
    assert expected_output_ids_for_config({"mode": "until_datetime"}) == ["wakeup"]
    assert expected_output_ids_for_config({"mode": "event"}) == ["event"]
    assert expected_output_ids_for_config({"mode": "event_or_timeout"}) == ["event", "timeout"]
    # Legacy (no mode key) -> wakeup
    assert expected_output_ids_for_config({"duration_hours": 4}) == ["wakeup"]
    with pytest.raises(ValueError):
        expected_output_ids_for_config({"mode": "absurd"})


# ── duration_value + duration_unit tests ──────────────────────────────────────

def test_duration_value_minutes():
    cfg = _wait_config(mode="duration", duration_value=30, duration_unit="minutes")
    assert cfg.duration_value == 30
    assert cfg.duration_unit == "minutes"


def test_duration_value_hours():
    cfg = _wait_config(mode="duration", duration_value=2, duration_unit="hours")
    assert cfg.duration_value == 2
    assert cfg.duration_unit == "hours"


def test_duration_value_days():
    cfg = _wait_config(mode="duration", duration_value=3, duration_unit="days")
    assert cfg.duration_value == 3
    assert cfg.duration_unit == "days"


def test_legacy_duration_hours_coerces_to_value_unit():
    """Legacy duration_hours coerces → value+unit with unit='hours'."""
    cfg = _wait_config(duration_hours=4)
    assert cfg.duration_value == 4
    assert cfg.duration_unit == "hours"
    # duration_hours is kept for back-compat reads
    assert cfg.duration_hours == 4


def test_duration_mode_requires_value_or_legacy_hours():
    """duration mode without any value field raises."""
    with pytest.raises(Exception):
        _wait_config(mode="duration")


def test_duration_unit_invalid_value_raises():
    with pytest.raises(Exception):
        _wait_config(mode="duration", duration_value=5, duration_unit="weeks")


def test_duration_timedelta_minutes():
    """Runtime timedelta is correct for minutes."""
    from datetime import timedelta
    from app.services.orchestration.nodes.logic_wait import _duration_timedelta
    assert _duration_timedelta(90, "minutes") == timedelta(minutes=90)


def test_duration_timedelta_hours():
    from datetime import timedelta
    from app.services.orchestration.nodes.logic_wait import _duration_timedelta
    assert _duration_timedelta(2.5, "hours") == timedelta(hours=2.5)


def test_duration_timedelta_days():
    from datetime import timedelta
    from app.services.orchestration.nodes.logic_wait import _duration_timedelta
    assert _duration_timedelta(7, "days") == timedelta(days=7)


# ── resume_poller wakeup-edge routing (BLOCKER B2) ────────────────────────────


def _wait_definition(node_type="logic.wait"):
    """A wait node with both event_or_timeout output edges, written the way the
    FE persists them: ``output_id`` only, no ``label``."""
    return {
        "nodes": [
            {"id": "w1", "type": node_type, "config": {}},
            {"id": "after_event", "type": "sink.complete", "config": {}},
            {"id": "after_timeout", "type": "sink.complete", "config": {}},
        ],
        "edges": [
            {"source": "w1", "target": "after_event", "output_id": "event"},
            {"source": "w1", "target": "after_timeout", "output_id": "timeout"},
        ],
    }


def test_wakeup_edge_event_or_timeout_routes_timeout_branch():
    from app.services.orchestration.resume_poller import _wakeup_edge_target
    target = _wakeup_edge_target(_wait_definition(), "w1", woke_by="timeout")
    assert target == "after_timeout"


def test_wakeup_edge_event_or_timeout_routes_event_branch():
    from app.services.orchestration.resume_poller import _wakeup_edge_target
    target = _wakeup_edge_target(_wait_definition(), "w1", woke_by="event")
    assert target == "after_event"


def test_wakeup_edge_single_output_duration_routes_wakeup():
    """A duration wait has one ``wakeup`` edge; both wake reasons resolve to it."""
    from app.services.orchestration.resume_poller import _wakeup_edge_target
    definition = {
        "nodes": [
            {"id": "w1", "type": "logic.wait", "config": {}},
            {"id": "next", "type": "sink.complete", "config": {}},
        ],
        "edges": [{"source": "w1", "target": "next", "output_id": "wakeup"}],
    }
    assert _wakeup_edge_target(definition, "w1", woke_by="timeout") == "next"
    assert _wakeup_edge_target(definition, "w1", woke_by="event") == "next"


def test_wakeup_edge_legacy_label_only_resolves():
    """Pre-normalizer edges carry ``label`` and no ``output_id`` — still resolve."""
    from app.services.orchestration.resume_poller import _wakeup_edge_target
    definition = {
        "nodes": [
            {"id": "w1", "type": "logic.wait", "config": {}},
            {"id": "next", "type": "sink.complete", "config": {}},
        ],
        "edges": [{"source": "w1", "target": "next", "label": "wakeup"}],
    }
    assert _wakeup_edge_target(definition, "w1", woke_by="timeout") == "next"


def test_wakeup_edge_non_wait_node_uses_success():
    """Action nodes flipped to ready via webhook advance along the success edge."""
    from app.services.orchestration.resume_poller import _wakeup_edge_target
    definition = {
        "nodes": [
            {"id": "a1", "type": "messaging.send_whatsapp_template", "config": {}},
            {"id": "ok", "type": "sink.complete", "config": {}},
            {"id": "bad", "type": "sink.complete", "config": {}},
        ],
        "edges": [
            {"source": "a1", "target": "bad", "output_id": "failed"},
            {"source": "a1", "target": "ok", "output_id": "success"},
        ],
    }
    assert _wakeup_edge_target(definition, "a1", woke_by="event") == "ok"


def test_wakeup_edge_event_or_timeout_no_output_id_match_falls_back():
    """If neither output_id matches the reason, fall back to first outgoing edge."""
    from app.services.orchestration.resume_poller import _wakeup_edge_target
    definition = {
        "nodes": [{"id": "w1", "type": "logic.wait", "config": {}}],
        "edges": [
            {"source": "w1", "target": "only", "output_id": "wakeup"},
        ],
    }
    # event_or_timeout reason 'event' has no 'event' edge here → fall back.
    assert _wakeup_edge_target(definition, "w1", woke_by="event") == "only"
