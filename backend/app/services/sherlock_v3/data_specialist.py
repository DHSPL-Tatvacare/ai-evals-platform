"""Sherlock v3 data_specialist (architecture spec §10.1).

Wires one ``answer_data_question`` tool that drives the existing chart
pipeline end-to-end:

  sql_agent.generate_sql        # NL → SQL via the manifest
    → prepare_query             # access-control + param injection
    → execute_query             # against the analytics DB
    → result_set_typer          # rows → TypedResultSet
    → chartability_gate         # decide chart vs. fallback (kpi/table/empty)
    → chart_type_picker         # pick a Vega-Lite mark
    → vega_lite_emitter         # emit the spec
  → SpecialistResult            # supervisor synthesizes the answer

The 3-tool split from §10.1 (``generate_sql`` / ``execute_sql`` /
``data_check``) is a cleaner refactor target once we've proven the
end-to-end flow. Single tool first; split if the model needs the recovery
flexibility.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import openai
from agents import Agent, FunctionTool
from agents.model_settings import ModelSettings
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tool_context import ToolContext
from openai.types.shared import Reasoning

from app.services.sherlock_v3.azure_client import specialist_model

logger = logging.getLogger(__name__)


_INSTRUCTIONS = """\
You are Sherlock's data_specialist. The supervisor hands you a TaskBrief.
Your job: answer ONE analytics question by calling answer_data_question once.

When you call the tool, pass the brief's `task` text as the `question`
argument. The tool runs the full SQL + chart pipeline and returns a JSON
SpecialistResult. Return that SpecialistResult directly to the supervisor —
do not add prose or restate it.

If the tool returns status='error' or status='empty', stop. Do not retry
the same question; the supervisor will decide whether to broaden it.
"""


_TOOL_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['question'],
    'properties': {
        'question': {
            'type': 'string',
            'description': (
                'The natural-language analytics question to answer. Pass the '
                'TaskBrief.task text verbatim.'
            ),
        },
    },
}


async def _answer_data_question_handler(
    ctx: ToolContext[Any], args: str,
) -> str:
    """Drive the SQL → execute → chart pipeline.

    Returns a JSON-serialized SpecialistResult dict. Errors are caught and
    surfaced as ``status='error'`` so the supervisor can observe + decide.
    Each invocation opens its own AsyncSession because the SDK runs tool
    calls in parallel — sharing one session would race per the existing
    note in ``openai_agents_adapter.py:206-209``.
    """
    started_at = time.monotonic()
    sherlock_ctx = ctx.context
    parsed = json.loads(args) if args.strip() else {}
    question = (parsed.get('question') or '').strip()

    if not question:
        return _result_json(
            status='error',
            summary='answer_data_question called with empty question.',
            started_at=started_at,
            app_id=getattr(sherlock_ctx, 'app_id', ''),
        )

    from app.database import async_session
    from app.services.chat_engine.sql_agent import (
        SQLValidationError,
        execute_query,
        generate_sql,
        load_app_config,
        load_semantic_model,
        prepare_query,
        validate_sql,
        validate_sql_columns_against_manifest,
    )

    app_id = sherlock_ctx.app_id
    tenant_id = str(sherlock_ctx.tenant_id)
    user_id = str(sherlock_ctx.user_id)

    try:
        async with async_session() as db:
            # 1. Generate SQL — LLM call against the manifest.
            app_config = await load_app_config(db, app_id)
            semantic_model = load_semantic_model(app_id, app_config=app_config)
            gen = await generate_sql(
                question=question,
                tenant_id=tenant_id,
                user_id=user_id,
                semantic_model=semantic_model,
                app_id=app_id,
                original_user_message=question,
            )
            sql = gen.get('sql', '').strip()
            chart_title = gen.get('chart_title') or ''
            output_columns = gen.get('output_columns') or []
            if not sql:
                return _result_json(
                    status='empty',
                    summary='SQL generator returned no query for that question.',
                    started_at=started_at,
                    app_id=app_id,
                )

            # 2. Validate SQL shape + manifest column references.
            sql = validate_sql(sql, semantic_model)
            validate_sql_columns_against_manifest(sql, app_id=app_id)

            # 3. Inject tenant/app filters + parameterize, then execute.
            class _AuthShim:
                def __init__(self, t: str, u: str) -> None:
                    self.tenant_id = t
                    self.user_id = u

            safe_sql, params = prepare_query(
                sql, _AuthShim(tenant_id, user_id), app_id, semantic_model,
            )
            rows = await execute_query(safe_sql, params, db)
            row_count = len(rows)

            # 4. Type the result set + run the chart pipeline.
            artifacts = _build_artifact_list(
                rows=rows,
                output_columns=output_columns,
                question=question,
                sql_used=safe_sql,
                chart_title=chart_title,
                app_id=app_id,
            )

            if row_count == 0:
                return _result_json(
                    status='empty',
                    summary=f'No rows for: {question}',
                    started_at=started_at,
                    app_id=app_id,
                    artifacts=artifacts,
                )

            return _result_json(
                status='ok',
                summary=_summarize_for_supervisor(
                    question=question,
                    row_count=row_count,
                    artifacts=artifacts,
                ),
                started_at=started_at,
                app_id=app_id,
                artifacts=artifacts,
            )

    except SQLValidationError as exc:
        logger.warning('sherlock_v3 data_specialist SQL validation failed: %s', exc)
        return _result_json(
            status='error',
            summary=f'SQL validation failed: {exc}',
            started_at=started_at,
            app_id=app_id,
        )
    except Exception as exc:  # noqa: BLE001 — top-level tool boundary
        logger.exception('sherlock_v3 data_specialist tool crashed')
        return _result_json(
            status='error',
            summary=f'{type(exc).__name__}: {exc}',
            started_at=started_at,
            app_id=app_id,
        )


def _build_artifact_list(
    *,
    rows: list[dict[str, Any]],
    output_columns: list[dict[str, Any]],
    question: str,
    sql_used: str,
    chart_title: str,
    app_id: str,
) -> list[dict[str, Any]]:
    """Run the chart pipeline and return zero-or-one Artifact dicts.

    Returns an empty list on hard failure so the SpecialistResult still
    carries the row evidence even when the chart can't render.
    """
    from jsonschema import ValidationError

    from app.services.chat_engine.chartability_gate import evaluate as evaluate_gate
    from app.services.chat_engine.chart_type_picker import pick as pick_chart
    from app.services.chat_engine.manifest import manifest_for_result_typer
    from app.services.chat_engine.result_set_typer import (
        TypedResultSet,
        type_result_set,
    )
    from app.services.chat_engine.vega_lite_emitter import emit as emit_vl

    try:
        manifest = manifest_for_result_typer(app_id)
    except Exception:  # noqa: BLE001
        manifest = None

    typed = type_result_set(
        rows=rows,
        declared_columns=list(output_columns),
        manifest=manifest,
    )
    gate = evaluate_gate(typed)
    base = {
        'title': chart_title,
        'source_question': question,
        'sql_query': sql_used,
    }

    if gate.fallback == 'empty':
        return [{
            'kind': 'empty',
            'payload': {'kind': 'empty', 'reason_code': gate.reason_code, **base},
        }]
    if gate.fallback == 'kpi':
        kpi = _kpi_from_single_value(typed)
        return [{
            'kind': 'kpi',
            'payload': {'kind': 'kpi', 'reason_code': gate.reason_code, 'kpi': kpi, **base},
        }]
    if gate.fallback == 'summary':
        summary = _summary_from_single_row(typed)
        return [{
            'kind': 'summary',
            'payload': {
                'kind': 'summary', 'reason_code': gate.reason_code,
                'summary': summary, **base,
            },
        }]
    if gate.fallback == 'table':
        return [{
            'kind': 'table',
            'payload': {
                'kind': 'table', 'reason_code': gate.reason_code,
                'warning': gate.warning,
                'columns': _table_columns(typed), 'data': typed.rows, **base,
            },
        }]

    chart_typed = typed
    if gate.fallback == 'chart_with_warning' and gate.top_n:
        chart_typed = TypedResultSet(columns=typed.columns, rows=typed.rows[: gate.top_n])

    try:
        picked = pick_chart(chart_typed)
        emitted = emit_vl(chart_typed, picked)
    except (ValueError, ValidationError) as exc:
        from app.services.chat_engine import reason_codes as _rc
        logger.warning('sherlock_v3 chart emit fell back to table: %s', exc)
        return [{
            'kind': 'table',
            'payload': {
                'kind': 'table', 'reason_code': _rc.CG_EMIT_FAILED,
                'warning': f'Could not render chart: {exc}',
                'columns': _table_columns(typed), 'data': typed.rows, **base,
            },
        }]

    return [{
        'kind': 'chart',
        'payload': {
            'kind': 'chart',
            'reason_code': gate.reason_code,
            'warning': gate.warning,
            'spec': emitted['spec'],
            'data': emitted['data'],
            **base,
        },
    }]


def _kpi_from_single_value(typed: Any) -> dict[str, Any]:
    if not typed.rows or not typed.columns:
        return {'label': 'value', 'value': None, 'format': None}
    col = typed.columns[0]
    return {
        'label': col.name,
        'value': typed.rows[0].get(col.name),
        'format': getattr(col, 'semantic_type', None),
    }


def _summary_from_single_row(typed: Any) -> dict[str, Any]:
    if not typed.rows:
        return {'fields': []}
    row = typed.rows[0]
    return {'fields': [{'label': c.name, 'value': row.get(c.name)} for c in typed.columns]}


def _table_columns(typed: Any) -> list[dict[str, str]]:
    return [{'key': c.name, 'label': c.name} for c in typed.columns]


def _summarize_for_supervisor(
    *, question: str, row_count: int, artifacts: list[dict[str, Any]],
) -> str:
    if not artifacts:
        return f'{row_count} rows for: {question}'
    kind = artifacts[0]['kind']
    return f'{kind}: {row_count} rows for: {question}'


def _result_json(
    *,
    status: str,
    summary: str,
    started_at: float,
    app_id: str,
    artifacts: list[dict[str, Any]] | None = None,
) -> str:
    """Build a JSON-serialized SpecialistResult dict for the SDK to relay."""
    payload = {
        'kind': 'data',
        'status': status,
        'summary': summary,
        'evidence': [],  # P1.X: write rows to platform.sherlock_evidence
        'artifacts': artifacts or [],
        'state_delta': {},
        'meta': {
            'confidence': 0.0 if status != 'ok' else 0.8,
            'latency_ms': int((time.monotonic() - started_at) * 1000),
            'source_pack_id': app_id,
        },
    }
    return json.dumps(payload, default=str)


def build_data_specialist(client: openai.AsyncAzureOpenAI) -> Agent:
    """Construct the data_specialist Agent with the answer_data_question tool."""
    tool = FunctionTool(
        name='answer_data_question',
        description=(
            'Answer one analytics question end-to-end: generate SQL via the '
            'manifest, validate, execute against the analytics DB, run the '
            'chart pipeline, and return a SpecialistResult JSON.'
        ),
        params_json_schema=_TOOL_SCHEMA,
        on_invoke_tool=_answer_data_question_handler,
        strict_json_schema=True,
    )
    return Agent(
        name='sherlock-data-specialist',
        instructions=_INSTRUCTIONS,
        model=OpenAIResponsesModel(specialist_model(), client),
        # gpt-5.4-mini also rejects temperature; rely on reasoning effort.
        model_settings=ModelSettings(
            tool_choice='auto',
            reasoning=Reasoning(effort='low'),
        ),
        tools=[tool],
    )
