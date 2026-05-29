"""Unit tests for the analytics date-window parser (no DB)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.routes.orchestration_analytics import _parse_window


def test_date_only_to_advances_to_next_midnight():
    # Date-only "to" must become an exclusive next-midnight bound so today is in range.
    start, end = _parse_window("2026-04-29", "2026-05-29")
    assert start == datetime(2026, 4, 29, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 30, tzinfo=timezone.utc)


def test_explicit_datetime_to_passes_through():
    _, end = _parse_window("2026-04-29", "2026-05-29T13:45:00")
    assert end == datetime(2026, 5, 29, 13, 45, tzinfo=timezone.utc)


def test_absent_to_defaults_to_now():
    before = datetime.now(timezone.utc)
    _, end = _parse_window("2026-04-29", None)
    after = datetime.now(timezone.utc)
    assert before <= end <= after
