"""Compile the shared predicate AST to an injection-safe SQL boolean expression.

The resolved filter lives inside a stored matview/view definition, which cannot take bind
parameters — so values render as validated, escaped SQL literals. Injection-safety is the
load-bearing property, hence the explicit adversarial cases.
"""
import pytest

from app.services.orchestration.predicate_contract import PredicateError
from app.services.orchestration.predicate_sql import PredicateSqlError, compile_predicate

# Maps an allowed (resolved) field name -> the underlying column expression it projects from.
COLS = {
    "lead_stage": "l.lead_stage",
    "score": "e.num_01",
    "condition": "e.txt_01",
    "converted": "l.converted",
}


def test_leaf_eq_string_renders_quoted_literal():
    assert compile_predicate({"field": "lead_stage", "op": "eq", "value": "lost"}, COLS) == "l.lead_stage = 'lost'"


def test_leaf_neq_string():
    assert compile_predicate({"field": "lead_stage", "op": "neq", "value": "lost"}, COLS) == "l.lead_stage <> 'lost'"


def test_numeric_comparisons():
    assert compile_predicate({"field": "score", "op": "gte", "value": 50}, COLS) == "e.num_01 >= 50"
    assert compile_predicate({"field": "score", "op": "lt", "value": 2.5}, COLS) == "e.num_01 < 2.5"


def test_in_and_not_in_render_lists():
    assert (
        compile_predicate({"field": "lead_stage", "op": "in", "value": ["won", "lost"]}, COLS)
        == "l.lead_stage IN ('won', 'lost')"
    )
    assert (
        compile_predicate({"field": "lead_stage", "op": "not_in", "value": ["won"]}, COLS)
        == "l.lead_stage NOT IN ('won')"
    )


def test_contains_uses_position_not_like():
    # POSITION avoids LIKE wildcard semantics (% / _) leaking from user input.
    assert (
        compile_predicate({"field": "condition", "op": "contains", "value": "diab"}, COLS)
        == "POSITION('diab' IN e.txt_01) > 0"
    )


def test_exists_and_missing_render_null_checks():
    assert compile_predicate({"field": "condition", "op": "exists"}, COLS) == "e.txt_01 IS NOT NULL"
    assert compile_predicate({"field": "condition", "op": "missing"}, COLS) == "e.txt_01 IS NULL"


def test_boolean_literal():
    assert compile_predicate({"field": "converted", "op": "eq", "value": True}, COLS) == "l.converted = TRUE"
    assert compile_predicate({"field": "converted", "op": "eq", "value": False}, COLS) == "l.converted = FALSE"


def test_and_or_not_nesting_is_parenthesised():
    pred = {
        "and": [
            {"field": "lead_stage", "op": "in", "value": ["won", "lost"]},
            {
                "or": [
                    {"field": "score", "op": "gte", "value": 50},
                    {"not": {"field": "converted", "op": "eq", "value": True}},
                ]
            },
        ]
    }
    assert (
        compile_predicate(pred, COLS)
        == "(l.lead_stage IN ('won', 'lost') AND (e.num_01 >= 50 OR (NOT l.converted = TRUE)))"
    )


def test_unknown_field_rejected():
    with pytest.raises(PredicateSqlError):
        compile_predicate({"field": "ssn", "op": "eq", "value": "x"}, COLS)


def test_string_literal_is_injection_safe():
    sql = compile_predicate({"field": "lead_stage", "op": "eq", "value": "x'; DROP TABLE crm_lead; --"}, COLS)
    # The inner quote is doubled, so the whole payload is one inert string literal.
    assert sql == "l.lead_stage = 'x''; DROP TABLE crm_lead; --'"
    assert sql.count("'") == 4  # opening + doubled-inner + closing


def test_in_list_injection_safe():
    sql = compile_predicate({"field": "lead_stage", "op": "in", "value": ["a", "b'); --"]}, COLS)
    assert sql == "l.lead_stage IN ('a', 'b''); --')"


def test_malformed_predicate_rejected():
    with pytest.raises(PredicateSqlError):
        compile_predicate({"field": "score", "op": "in", "value": []}, COLS)  # empty in-list


def test_non_finite_number_rejected():
    with pytest.raises(PredicateSqlError):
        compile_predicate({"field": "score", "op": "gt", "value": float("inf")}, COLS)


def test_predicate_sql_error_is_a_predicate_error():
    # Callers that already catch PredicateError keep working.
    assert issubclass(PredicateSqlError, PredicateError)
