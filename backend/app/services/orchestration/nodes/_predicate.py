"""Predicate evaluator — used by filter.eligibility, filter.consent_gate, and logic.conditional.

Predicate shape (recursive):
  {field, op, value}                    # leaf
  {and: [predicate, ...]}               # all true
  {or:  [predicate, ...]}               # any true
  {not: predicate}                      # negation

Supported leaf ops:
  eq, neq, gte, gt, lte, lt, in, not_in, contains, exists, missing

Missing fields evaluate to False for all leaf ops EXCEPT 'missing' (true) and 'exists' (false).
This is intentional — silent missing-data is a footgun; the canvas should expose 'exists'/'missing'
explicitly when the user wants to handle missing data.
"""
from __future__ import annotations

from typing import Any


class PredicateError(ValueError):
    pass


_LEAF_OPS = {"eq", "neq", "gte", "gt", "lte", "lt", "in", "not_in", "contains", "exists", "missing"}


def evaluate_predicate(predicate: dict[str, Any], payload: dict[str, Any]) -> bool:
    if not isinstance(predicate, dict):
        raise PredicateError(f"predicate must be dict, got {type(predicate).__name__}")

    if "and" in predicate:
        clauses = predicate["and"]
        if not isinstance(clauses, list) or not clauses:
            raise PredicateError("'and' requires non-empty list of clauses")
        return all(evaluate_predicate(c, payload) for c in clauses)

    if "or" in predicate:
        clauses = predicate["or"]
        if not isinstance(clauses, list) or not clauses:
            raise PredicateError("'or' requires non-empty list of clauses")
        return any(evaluate_predicate(c, payload) for c in clauses)

    if "not" in predicate:
        return not evaluate_predicate(predicate["not"], payload)

    op = predicate.get("op")
    field = predicate.get("field")
    if op is None or field is None:
        raise PredicateError(f"leaf predicate must have 'field' and 'op': {predicate!r}")
    if op not in _LEAF_OPS:
        raise PredicateError(f"unsupported op: {op!r}")

    value = predicate.get("value")
    actual = payload.get(field)

    if op == "exists":
        return actual is not None
    if op == "missing":
        return actual is None
    if actual is None:
        return False

    if op == "eq":
        return actual == value
    if op == "neq":
        return actual != value
    if op == "gte":
        return actual >= value
    if op == "gt":
        return actual > value
    if op == "lte":
        return actual <= value
    if op == "lt":
        return actual < value
    if op == "in":
        if not isinstance(value, list):
            raise PredicateError("'in' requires list value")
        return actual in value
    if op == "not_in":
        if not isinstance(value, list):
            raise PredicateError("'not_in' requires list value")
        return actual not in value
    if op == "contains":
        if not isinstance(actual, str) or not isinstance(value, str):
            return False
        return value in actual

    raise PredicateError(f"unhandled op: {op!r}")  # unreachable
