"""Validation-contract tests for logic.wait — empty-string optional fields drop.

Pure model_validate tests; no DB. Guards the publish-unblock fix where a
stray empty ``until_datetime`` (left behind by a mode switch in the editor)
must coerce to None instead of failing the strict datetime parse.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    future = datetime.now(timezone.utc) + timedelta(days=365)
    cfg = _Config.model_validate(
        {"mode": "until_datetime", "until_datetime": future.isoformat()}
    )
    assert cfg.until_datetime is not None
    assert cfg.until_datetime.year == future.year


def _past_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def _future_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def test_publish_rejects_past_until_datetime():
    """Publish-mode validation must reject a wake time already in the past."""
    with pytest.raises(ValueError):
        _Config.model_validate(
            {"mode": "until_datetime", "until_datetime": _past_iso()},
            context={"mode": "publish"},
        )


def test_publish_accepts_future_until_datetime():
    cfg = _Config.model_validate(
        {"mode": "until_datetime", "until_datetime": _future_iso()},
        context={"mode": "publish"},
    )
    assert cfg.until_datetime is not None


def test_draft_tolerates_past_until_datetime():
    """Draft mode keeps its tolerance — a past wake time saves without error."""
    cfg = _Config.model_validate(
        {"mode": "until_datetime", "until_datetime": _past_iso()},
        context={"mode": "draft"},
    )
    assert cfg.until_datetime is not None


class _FakeCtx:
    """Minimal ctx for execute(): records set_recipient_state calls, no DB I/O."""

    def __init__(self) -> None:
        self.db = None
        self.run_id = "run-1"
        self.states: list[dict] = []

    async def set_recipient_state(self, rid, *, status, wakeup_at):
        self.states.append({"rid": rid, "status": status, "wakeup_at": wakeup_at})


async def _one_recipient():
    yield ("r1", {})


@pytest.mark.asyncio
async def test_runtime_past_until_datetime_wakes_immediately(monkeypatch):
    """At runtime a past until_datetime must resolve to a past wakeup_at (picked
    up immediately by the resume poller) — it must never raise."""
    import app.services.orchestration.dispatch.resume_enqueue as resume_enqueue

    async def _noop_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr(resume_enqueue, "enqueue_resume_for_recipient", _noop_enqueue)

    # Construct with NO context — exactly how the runtime engine builds it
    # (traversal.py / event_resume.py / run_handler.py). Must not raise on a
    # past instant; the publish guard is scoped to context mode='publish' only.
    cfg = _Config.model_validate(
        {"mode": "until_datetime", "until_datetime": _past_iso()},
    )
    from app.services.orchestration.nodes.logic_wait import _Handler

    ctx = _FakeCtx()
    result = await _Handler().execute(_one_recipient(), cfg, ctx)
    assert result.suspended is True
    assert ctx.states[0]["wakeup_at"] < datetime.now(timezone.utc)
