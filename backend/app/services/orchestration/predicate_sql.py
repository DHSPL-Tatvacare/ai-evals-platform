"""Compile the shared predicate AST into an injection-safe SQL boolean expression.

Used where a predicate must live inside a stored definition — a materialized view / view
``WHERE`` — that cannot take bind parameters. Values are therefore rendered as validated,
escaped SQL literals, never interpolated raw. Pure; depends only on ``predicate_contract``.

``compile_predicate(predicate, columns)`` takes a map of allowed (resolved) field name to the
underlying column expression it projects from, e.g. ``{"condition": "e.txt_01"}``. A field
outside that map is rejected, so a filter can only reference real, mapped columns.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from app.services.orchestration.predicate_contract import (
    AndPredicate,
    LeafPredicate,
    NotPredicate,
    OrPredicate,
    Predicate,
    PredicateError,
    parse,
)


class PredicateSqlError(PredicateError):
    pass


def compile_predicate(predicate: Any, columns: Mapping[str, str]) -> str:
    """Return a SQL boolean expression for ``predicate`` over ``columns``."""
    if isinstance(predicate, (LeafPredicate, AndPredicate, OrPredicate, NotPredicate)):
        node: Predicate = predicate
    else:
        try:
            node = parse(predicate)
        except PredicateError as exc:
            raise PredicateSqlError(str(exc)) from exc
    return _compile(node, columns)


def _compile(node: Predicate, columns: Mapping[str, str]) -> str:
    if isinstance(node, AndPredicate):
        return "(" + " AND ".join(_compile(c, columns) for c in node.and_) + ")"
    if isinstance(node, OrPredicate):
        return "(" + " OR ".join(_compile(c, columns) for c in node.or_) + ")"
    if isinstance(node, NotPredicate):
        return "(NOT " + _compile(node.not_, columns) + ")"
    return _compile_leaf(node, columns)


def _compile_leaf(leaf: LeafPredicate, columns: Mapping[str, str]) -> str:
    col = columns.get(leaf.field)
    if col is None:
        raise PredicateSqlError(f"field {leaf.field!r} is not a mapped column")

    op = leaf.op
    if op == "exists":
        return f"{col} IS NOT NULL"
    if op == "missing":
        return f"{col} IS NULL"
    if op == "eq":
        return f"{col} = {_lit(leaf.value)}"
    if op == "neq":
        return f"{col} <> {_lit(leaf.value)}"
    if op == "gte":
        return f"{col} >= {_lit(leaf.value)}"
    if op == "gt":
        return f"{col} > {_lit(leaf.value)}"
    if op == "lte":
        return f"{col} <= {_lit(leaf.value)}"
    if op == "lt":
        return f"{col} < {_lit(leaf.value)}"
    if op == "in":
        return f"{col} IN ({', '.join(_lit(v) for v in leaf.value)})"
    if op == "not_in":
        return f"{col} NOT IN ({', '.join(_lit(v) for v in leaf.value)})"
    if op == "contains":
        return f"POSITION({_lit(leaf.value)} IN {col}) > 0"
    raise PredicateSqlError(f"unsupported op: {op!r}")  # unreachable — parse() gates ops


def _lit(value: Any) -> str:
    """Render a scalar as a safe SQL literal. Booleans before ints (bool is an int subclass)."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PredicateSqlError("non-finite numeric value is not a valid SQL literal")
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise PredicateSqlError(f"unsupported literal type: {type(value).__name__}")


__all__ = ["PredicateSqlError", "compile_predicate"]
