"""Build the static system prompt for the data_specialist agent.

Bakes the per-app schema, allowed tables, column role hints, verified-
query exemplars, business semantics, and the output-column contract
into one string. The data_specialist's LLM uses this prompt to generate
SQL inline — there is no second LLM call. ``submit_sql`` is a pure
helper that runs the bouncer + executes + charts whatever SQL the LLM
emitted.

Phase 3 (workbench era): the prose "SQL safety rules" that used to live
here are gone. The bouncer (``sql_bouncer.check_before`` /
``check_after``) is now the single deterministic safety surface — every
rule about allowed tables, allowed columns, declared joins, fan/chasm
traps, tenant/app filters, and honest row caps is enforced structurally,
not by asking the LLM to read prose. What stays:

  * catalog (schema + allowed tables + role hints)
  * verified-query exemplars
  * output-column contract
  * business semantics (app-specific custom instructions)
"""
from __future__ import annotations

from typing import Any

import yaml

from app.services.chat_engine.sql_agent import BINDER_CONTRACT
from app.services.chat_engine.sql_bouncer import RULE_TEACH


def _indent(text: str, n: int) -> str:
    pad = ' ' * n
    return '\n'.join(pad + line for line in text.splitlines())


_PERSONALITY = """\
You are Sherlock's data_specialist. The supervisor hands you a
SpecialistBrief JSON envelope with this shape:

  {
    "question":      "<the analytics question to answer>",
    "scope":         {"tenant_id":"...","app_id":"...","user_id":"..."},
    "prior_attempts": [ {"sql":"...","verdict":{...},"status":"...","error_message":"..."} ],
    "retry_hint":    "<optional one-line correction guidance>"
  }

When ``prior_attempts`` is non-empty, you are retrying. Read each prior
Attempt's ``verdict.diagnostic`` (rule_id, available_tables,
available_columns_for, did_you_mean, missing_group_by_keys, required_scope_predicates)
PLUS the ``retry_hint`` and fix the SQL to satisfy all of them.

You have ONE tool: ``submit_sql``. Submit the SQL you generated with its
``output_columns`` manifest, ``declared_grain`` (logical columns that
uniquely identify one result row), ``expected_row_bound``, and a short
``chart_title``. The bouncer checks the query DETERMINISTICALLY before and
after execution and hands back a typed Diagnostic — a rejection is feedback,
not a failure: it names the positive recovery surface (what IS allowed). Fix
the SQL and resubmit ``submit_sql`` in the same way, looping until it passes
or you reach the attempt cap. The last ``submit_sql`` call returns a
SpecialistResult JSON with the attempt trail; that IS your output — return it
verbatim.
"""

_OUTPUT_CONTRACT = """\
TOOL CALL FORMAT for ``submit_sql``:

  {{
    "sql": "<your SELECT or WITH … SELECT … query>",
    "declared_grain": ["<column name>", ...],
    "expected_row_bound": "<single|small|medium|large|unbounded>",
    "chart_title": "<≤ 8 word title for the result>",
    "output_columns": [
      {{
        "alias": "<column name as it appears in the SELECT result>",
        "role_hint": "<dimension|measure|temporal|ordered_categorical|key|identifier>",
        "type_hint": "<quantitative|temporal|ordinal|nominal|boolean|geo>",
        "source_column": "<table>.<column>", // ONLY for passthrough columns; omit for aggregates
        "semantic_type_hint": "<pk|fk|category|id_hash|currency|percent|lat|lon|count|ratio|score|duration|none>"
      }}
    ]
  }}

DECLARED_GRAIN RULES:
- For aggregate queries (GROUP BY): list every GROUP BY column.
- For per-row fact queries: list the catalog table's analytical_grain.
- For single-value KPI queries: pass an empty list.

EXPECTED_ROW_BOUND RULES:
- single   — one row only (KPI / scalar lookup).
- small    — ≤ 50 rows (e.g., per-agent rollup for a week).
- medium   — ≤ 500 rows.
- large    — ≤ 5,000 rows.
- unbounded — anything more; expect truncation.
The server picks the actual cap and tells you (more_rows_exist) if
the result was truncated.

OUTPUT_COLUMNS RULES:
- One entry per SELECT column, in SELECT order. ``alias`` must equal
  the result column name.
- Aggregates (COUNT/SUM/AVG/MIN/MAX) → role_hint="measure",
  type_hint="quantitative". Pick semantic_type from the aggregate kind:
  COUNT → "count", AVG of percent → "percent", etc.
- date_trunc / ::date / ::timestamp → role_hint="temporal",
  type_hint="temporal".
- UUID or *_id columns → role_hint="identifier", type_hint="nominal",
  semantic_type_hint="id_hash" (or "pk" / "fk" when obvious).
- Passthrough columns from a catalog table: include
  ``source_column="<table>.<column>"``.
- Aggregate columns (no passthrough source): omit ``source_column``.
"""

# A single-row run-id filter plus an IN-list of quoted UUIDs. parameterize_sql
# rewrites each quoted UUID literal into :uuid_N, so this is the binder's truth.
ENTITY_ID_FILTER_EXEMPLAR_SQL = (
    "SELECT agent, overall_score, created_at\n"
    "FROM analytics.fact_evaluation\n"
    "WHERE tenant_id = :tenant_id AND app_id = :app_id\n"
    "  AND run_id = '11111111-1111-1111-1111-111111111111'\n"
    "  AND evaluator_id IN ('22222222-2222-2222-2222-222222222222',\n"
    "                       '33333333-3333-3333-3333-333333333333')\n"
    "ORDER BY created_at DESC"
)


# Grain-correct GROUP BY (R5): every non-aggregated SELECT column is in
# GROUP BY; the aggregate stays on the table's analytical grain.
GRAIN_GROUP_BY_EXEMPLAR_SQL = (
    "SELECT agent,\n"
    "       COUNT(*) AS calls,\n"
    "       ROUND(AVG(overall_score)::numeric, 2) AS avg_score\n"
    "FROM analytics.fact_evaluation\n"
    "WHERE tenant_id = :tenant_id AND app_id = :app_id\n"
    "GROUP BY agent\n"
    "ORDER BY avg_score DESC"
)

# Multi-grain join (R6/R7s/R8): aggregate the fine-grain fact, join the
# coarse dimension on its declared key, scope BOTH aliases.
MULTI_GRAIN_JOIN_EXEMPLAR_SQL = (
    "SELECT dl.source,\n"
    "       COUNT(*) AS activity_count\n"
    "FROM analytics.fact_lead_activity la\n"
    "JOIN analytics.dim_lead dl ON la.lead_id = dl.lead_id\n"
    "WHERE la.tenant_id = :tenant_id AND la.app_id = :app_id\n"
    "  AND dl.tenant_id = :tenant_id AND dl.app_id = :app_id\n"
    "GROUP BY dl.source"
)


def _render_query_contract() -> str:
    """Render the query contract from the enforcers — one source of truth.

    The rule teaching comes from the bouncer (``RULE_TEACH``); the
    bound-param + quoting rule comes from the binder (``BINDER_CONTRACT``).
    This function only formats them; it authors no rule text.
    """
    rule_lines = '\n'.join(
        f'- {teach}' for _rule_id, teach in RULE_TEACH.items()
    )
    return (
        'QUERY CONTRACT (enforced by the bouncer — a rejection is feedback, '
        'not a failure):\n'
        + rule_lines + '\n\n'
        + 'PARAMETERS:\n- ' + BINDER_CONTRACT + '\n\n'
        + '  Example — filter by a resolved run_id (and an IN-list of '
        'run/evaluator ids):\n'
        + _indent(ENTITY_ID_FILTER_EXEMPLAR_SQL, 4) + '\n\n'
        + '  Example — grain-correct GROUP BY (every non-aggregated column '
        'grouped):\n'
        + _indent(GRAIN_GROUP_BY_EXEMPLAR_SQL, 4) + '\n\n'
        + '  Example — multi-grain join (aggregate the fine-grain fact, '
        'scope every alias):\n'
        + _indent(MULTI_GRAIN_JOIN_EXEMPLAR_SQL, 4) + '\n'
    )


def build_data_specialist_prompt(
    *,
    app_id: str,
    schema_context: dict[str, Any],
    allowed_tables: list[str],
    column_role_hints: list[str],
    exemplars: list[dict[str, str]],
    max_rows: int,
    grounding_header: str | None = None,
    instructions_block: str | None = None,
) -> str:
    """Compose the data_specialist's full system prompt for one app.

    ``grounding_header`` is rendered between the app scope and the
    catalog (workbench callers declare "WORKBENCH CATALOG IN EFFECT";
    legacy callers leave it unset).

    ``instructions_block`` is the residual business-semantics markdown
    rendered under an INSTRUCTIONS heading between the schema and the
    verified examples. Empty / None = no heading rendered.

    ``max_rows`` is unused — the bouncer's server-owned LIMIT is the
    authority on row caps — but kept for API stability.
    """
    del max_rows  # bouncer owns the row cap; parameter kept for stability.

    schema_yaml = yaml.dump(schema_context, default_flow_style=False, width=120, sort_keys=False)
    role_hints_block = '\n'.join(f'- {h}' for h in column_role_hints) or '- none'
    allowed_tables_block = ', '.join(sorted(allowed_tables))
    grounding_block = (grounding_header.strip() + '\n\n') if grounding_header else ''

    if exemplars:
        exemplar_lines: list[str] = ['VERIFIED QUERY EXAMPLES (hand-checked for this schema):']
        for ex in exemplars:
            exemplar_lines.append(f'\n  Q: {ex["question"]}')
            exemplar_lines.append(f'  SQL:\n{_indent(ex["sql"], 4)}')
        exemplars_block = '\n'.join(exemplar_lines)
    else:
        exemplars_block = 'VERIFIED QUERY EXAMPLES: (none for this app yet)'

    instructions_section = ''
    if instructions_block and instructions_block.strip():
        instructions_section = (
            'BUSINESS SEMANTICS (app-specific rules, apply on top of the catalog):\n'
            + instructions_block.strip() + '\n\n'
        )

    return (
        _PERSONALITY
        + '\n\n' + _OUTPUT_CONTRACT
        + '\n\n' + _render_query_contract()
        + '\nAPP SCOPE: ' + app_id + '\n\n'
        + grounding_block
        + '\nAllowed tables: ' + allowed_tables_block + '\n'
        + '\nColumn role hints:\n' + role_hints_block + '\n'
        + '\nSCHEMA (logical column names accepted by the bouncer):\n'
        + schema_yaml + '\n'
        + instructions_section
        + exemplars_block + '\n'
    )
