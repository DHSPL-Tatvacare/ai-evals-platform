# backend/tests/test_flag_utils.py
"""Tests for flag aggregation utilities.

Uses importlib to load flag_utils directly — the reports/__init__.py
imports ReportService which pulls in the full DB chain (asyncpg required).
flag_utils has zero dependencies so direct loading is safe.
"""

import importlib.util
import os

_path = os.path.join(
    os.path.dirname(__file__), '..', 'app', 'services', 'reports', 'flag_utils.py',
)
_spec = importlib.util.spec_from_file_location('flag_utils', _path)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

aggregate_flag = _mod.aggregate_flag
aggregate_outcome_flag = _mod.aggregate_outcome_flag


def test_aggregate_flag_counts_relevant_and_present():
    items = [
        {"present": True, "evidence": "heated exchange"},
        {"present": False, "evidence": "calm call"},
        {"present": "not_relevant"},
        {"present": True, "evidence": "raised voice"},
    ]
    result = aggregate_flag(items)
    assert result == {"relevant": 3, "notRelevant": 1, "present": 2}


def test_aggregate_flag_all_not_relevant():
    items = [{"present": "not_relevant"}, {"present": "not_relevant"}]
    result = aggregate_flag(items)
    assert result == {"relevant": 0, "notRelevant": 2, "present": 0}


def test_aggregate_flag_empty():
    assert aggregate_flag([]) == {"relevant": 0, "notRelevant": 0, "present": 0}


def test_aggregate_outcome_flag_dual_denominator():
    items = [
        {"attempted": True, "accepted": True, "evidence": "sold"},
        {"attempted": True, "accepted": False, "evidence": "declined"},
        {"attempted": False, "evidence": "no opportunity"},
        {"attempted": "not_relevant"},
    ]
    result = aggregate_outcome_flag(items, attempted_key="attempted", accepted_key="accepted")
    assert result == {"relevant": 3, "notRelevant": 1, "attempted": 2, "accepted": 1}


def test_aggregate_outcome_flag_simple_occurred():
    items = [
        {"occurred": True, "evidence": "meeting booked"},
        {"occurred": False, "evidence": "no meeting"},
        {"occurred": "not_relevant"},
    ]
    result = aggregate_outcome_flag(items, attempted_key="occurred")
    assert result == {"relevant": 2, "notRelevant": 1, "attempted": 1, "accepted": 0}
