"""Shared predicate evaluator for filter and logic nodes."""
from __future__ import annotations

import pytest

from app.services.orchestration.nodes._predicate import (
    PredicateError,
    evaluate_predicate,
)


def test_simple_eq():
    assert evaluate_predicate({"field": "mqlScore", "op": "eq", "value": 4}, {"mqlScore": 4}) is True


def test_simple_neq():
    assert evaluate_predicate({"field": "stage", "op": "neq", "value": "junk"}, {"stage": "warm"}) is True


def test_gte():
    assert evaluate_predicate({"field": "hba1c", "op": "gte", "value": 5.7}, {"hba1c": 6.5}) is True
    assert evaluate_predicate({"field": "hba1c", "op": "gte", "value": 5.7}, {"hba1c": 5.4}) is False


def test_in():
    assert evaluate_predicate({"field": "city", "op": "in", "value": ["Mumbai", "Delhi"]}, {"city": "Mumbai"}) is True
    assert evaluate_predicate({"field": "city", "op": "in", "value": ["Mumbai", "Delhi"]}, {"city": "Pune"}) is False


def test_not_in():
    assert evaluate_predicate({"field": "stage", "op": "not_in", "value": ["junk", "duplicate"]}, {"stage": "warm"}) is True


def test_contains():
    assert evaluate_predicate({"field": "notes", "op": "contains", "value": "diabetes"}, {"notes": "patient has diabetes type 2"}) is True


def test_missing_field_returns_false():
    assert evaluate_predicate({"field": "absent", "op": "eq", "value": "x"}, {"present": "y"}) is False


def test_and():
    p = {"and": [
        {"field": "mqlScore", "op": "gte", "value": 4},
        {"field": "city", "op": "eq", "value": "Mumbai"},
    ]}
    assert evaluate_predicate(p, {"mqlScore": 5, "city": "Mumbai"}) is True
    assert evaluate_predicate(p, {"mqlScore": 5, "city": "Pune"}) is False
    assert evaluate_predicate(p, {"mqlScore": 3, "city": "Mumbai"}) is False


def test_or():
    p = {"or": [
        {"field": "mqlScore", "op": "gte", "value": 4},
        {"field": "intent", "op": "eq", "value": "high"},
    ]}
    assert evaluate_predicate(p, {"mqlScore": 5, "intent": "low"}) is True
    assert evaluate_predicate(p, {"mqlScore": 2, "intent": "high"}) is True
    assert evaluate_predicate(p, {"mqlScore": 2, "intent": "low"}) is False


def test_not():
    assert evaluate_predicate({"not": {"field": "stage", "op": "eq", "value": "junk"}}, {"stage": "warm"}) is True


def test_unknown_op_raises():
    with pytest.raises(PredicateError):
        evaluate_predicate({"field": "x", "op": "regex_match", "value": ".+"}, {"x": "y"})


def test_malformed_predicate_raises():
    with pytest.raises(PredicateError):
        evaluate_predicate({"foo": "bar"}, {})
