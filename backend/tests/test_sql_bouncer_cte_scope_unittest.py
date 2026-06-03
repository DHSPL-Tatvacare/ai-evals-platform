"""Regression — bouncer R3/R4 must be CTE-scope-aware.

Locks the live prod failure (2026-06-02, turn 0d776964): the data_specialist's
"latest run" query references columns through CTE FROM-aliases (`lm.run_id`,
`lr.run_id`, `ds.*`) and joins catalog tables that live in *separate* CTE bodies.
The flat (non-scoped) R3/R4 falsely rejected every variant, so the turn failed
after 5 retries. The lowerer (semantic_lowering) already resolves these per-scope;
the bouncer must agree.
"""
from __future__ import annotations

import pytest

from app.services.chat_engine.granularity_graph import build_granularity_graph
from app.services.chat_engine.sql_bouncer import check_before
from app.services.chat_engine.workbench_catalog import load_workbench_catalog_strict


@pytest.fixture(scope='module')
def catalog():
    return load_workbench_catalog_strict('inside-sales')


@pytest.fixture(scope='module')
def graph(catalog):
    return build_granularity_graph(catalog)


def _diag(v):
    return (v.diagnostic.rule_id, v.diagnostic.message[:200]) if v.diagnostic else ('', '')


def test_cte_from_alias_qualified_columns_pass_r4(catalog, graph):
    """`FROM latest_meta lm ... SELECT lm.run_id` — lm is a CTE FROM-alias.
    R4 must treat lm/lr as CTE aliases, not undeclared catalog columns."""
    sql = """WITH latest_run AS (
        SELECT ar.run_id
        FROM analytics.agg_evaluation_run ar
        WHERE ar.tenant_id = :tenant_id AND ar.app_id = :app_id
        ORDER BY ar.completed_at DESC NULLS LAST
        LIMIT 1
    ), latest_meta AS (
        SELECT ar.run_id, ar.status, ar.avg_score
        FROM analytics.agg_evaluation_run ar
        JOIN latest_run lr ON ar.run_id = lr.run_id
        WHERE ar.tenant_id = :tenant_id AND ar.app_id = :app_id
    )
    SELECT lm.run_id, lm.status, lm.avg_score
    FROM latest_meta lm"""
    v = check_before(
        sql=sql, declared_grain=['run_id'], expected_row_bound='single',
        catalog=catalog, graph=graph,
    )
    assert v.ok, f'CTE FROM-alias query should pass; got {_diag(v)}'


def test_catalog_tables_in_separate_ctes_pass_r3(catalog, graph):
    """fact_evaluation and agg_evaluation_run live in DIFFERENT CTE bodies,
    joined only through a CTE — R3 must not demand a direct declared join
    between two tables that are never directly joined in any one scope."""
    sql = """WITH latest_run AS (
        SELECT ar.run_id
        FROM analytics.agg_evaluation_run ar
        WHERE ar.tenant_id = :tenant_id AND ar.app_id = :app_id
        ORDER BY ar.completed_at DESC NULLS LAST
        LIMIT 1
    ), dim_scores AS (
        SELECT fe.run_id, AVG(fe.call_opening_score) AS call_opening_score
        FROM analytics.fact_evaluation fe
        JOIN latest_run lr ON fe.run_id = lr.run_id
        WHERE fe.tenant_id = :tenant_id AND fe.app_id = :app_id
        GROUP BY fe.run_id
    )
    SELECT lr.run_id, ds.call_opening_score
    FROM latest_run lr
    LEFT JOIN dim_scores ds ON ds.run_id = lr.run_id"""
    v = check_before(
        sql=sql, declared_grain=['run_id'], expected_row_bound='single',
        catalog=catalog, graph=graph,
    )
    assert v.ok, f'separate-CTE catalog tables should pass R3; got {_diag(v)}'


def test_forbidden_column_inside_cte_body_still_rejected(catalog, graph):
    """Scope-awareness must not weaken security: a bogus catalog column
    referenced inside a CTE body is still rejected by R4."""
    sql = """WITH x AS (
        SELECT fe.totally_made_up_column AS made_up
        FROM analytics.fact_evaluation fe
        WHERE fe.tenant_id = :tenant_id AND fe.app_id = :app_id
    )
    SELECT made_up FROM x"""
    v = check_before(
        sql=sql, declared_grain=['run_id'], expected_row_bound='small',
        catalog=catalog, graph=graph,
    )
    assert not v.ok
    assert v.diagnostic.rule_number == 4
    assert any('totally_made_up_column' in c for c in v.diagnostic.offending_columns)


def test_two_catalog_tables_wrongly_joined_in_one_scope_still_rejected(catalog, graph):
    """Per-scope R3 must still catch a genuine bad join: two catalog tables
    joined in the SAME scope on undeclared columns."""
    sql = """SELECT fe.run_id
    FROM analytics.fact_evaluation fe
    JOIN analytics.agg_evaluation_run ar ON fe.agent = ar.run_name
    WHERE fe.tenant_id = :tenant_id AND fe.app_id = :app_id"""
    v = check_before(
        sql=sql, declared_grain=['run_id'], expected_row_bound='small',
        catalog=catalog, graph=graph,
    )
    assert not v.ok
    assert v.diagnostic.rule_number == 3
