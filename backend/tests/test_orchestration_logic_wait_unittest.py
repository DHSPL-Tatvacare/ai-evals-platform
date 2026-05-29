"""Validation-contract tests for logic.wait — empty-string optional fields drop.

Pure model_validate tests; no DB. Guards the publish-unblock fix where a
stray empty ``until_datetime`` (left behind by a mode switch in the editor)
must coerce to None instead of failing the strict datetime parse.
"""
from __future__ import annotations

import pytest

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.nodes.logic_wait import _Config


def test_blank_until_datetime_drops_in_duration_mode():
    """A stray empty until_datetime must not crash a valid duration config."""
    cfg = _Config.model_validate(
        {
            "mode": "duration",
            "duration_value": 15,
            "duration_unit": "minutes",
            "until_datetime": "",
        }
    )
    assert cfg.until_datetime is None
    assert cfg.duration_value == 15
    assert cfg.duration_unit == "minutes"


def test_blank_optional_numeric_drops():
    """Empty-string timeout_hours coerces to None rather than failing parse."""
    cfg = _Config.model_validate(
        {
            "mode": "duration",
            "duration_value": 1,
            "duration_unit": "hours",
            "timeout_hours": "",
            "duration_hours": "",
        }
    )
    assert cfg.timeout_hours is None


def test_blank_until_datetime_still_required_in_until_mode():
    """Dropping the blank does not paper over a genuinely missing required field."""
    with pytest.raises(ValueError):
        _Config.model_validate({"mode": "until_datetime", "until_datetime": ""})


def test_real_until_datetime_still_parses():
    cfg = _Config.model_validate(
        {"mode": "until_datetime", "until_datetime": "2026-05-01T00:00:00Z"}
    )
    assert cfg.until_datetime is not None
    assert cfg.until_datetime.year == 2026
