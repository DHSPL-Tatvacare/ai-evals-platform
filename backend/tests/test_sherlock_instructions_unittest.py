"""Phase 3 — instruction loader + prompt rendering.

Asserts:
  * App-default markdown is loaded by app_id.
  * Tenant override is concatenated AFTER the app default (later
    instruction wins on contradiction).
  * Empty result (missing file + null override) renders no INSTRUCTIONS
    heading at all (no stub noise).
  * The rendered prompt contains the sentinel app rule.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.constants import SYSTEM_TENANT_ID
from app.models.tenant_config import TenantConfiguration
from app.services.sherlock_v3.data_specialist_prompt import (
    build_data_specialist_prompt,
)
from app.services.sherlock_v3.instructions import load_instructions


@pytest_asyncio.fixture
async def reset_tenant_override(db_session):
    """Ensure SYSTEM_TENANT_ID has a tenant_configurations row with NULL
    sherlock_instructions before/after. The outer fixture's transaction
    rolls back, so test data does not leak."""
    existing = (await db_session.execute(
        select(TenantConfiguration.id).where(
            TenantConfiguration.tenant_id == SYSTEM_TENANT_ID,
        )
    )).scalar_one_or_none()
    if existing is None:
        db_session.add(TenantConfiguration(
            tenant_id=SYSTEM_TENANT_ID, allowed_domains=[],
        ))
        await db_session.commit()
    else:
        await db_session.execute(
            update(TenantConfiguration)
            .where(TenantConfiguration.tenant_id == SYSTEM_TENANT_ID)
            .values(sherlock_instructions=None)
        )
        await db_session.commit()
    yield


@pytest.mark.asyncio
async def test_app_default_loaded_for_known_app(
    db_session, reset_tenant_override,
) -> None:
    block = await load_instructions(
        'voice-rx', tenant_id=SYSTEM_TENANT_ID, db=db_session,
    )
    assert 'one decimal place' in block.lower()
    assert 'iso weeks' in block.lower()


@pytest.mark.asyncio
async def test_unknown_app_returns_empty(
    db_session, reset_tenant_override,
) -> None:
    block = await load_instructions(
        'this-app-has-no-md-file',
        tenant_id=SYSTEM_TENANT_ID,
        db=db_session,
    )
    assert block == ''


@pytest.mark.asyncio
async def test_tenant_override_appended_after_app_default(
    db_session, reset_tenant_override,
) -> None:
    sentinel = 'TENANT-OVERRIDE-SENTINEL-XYZ-' + uuid.uuid4().hex[:8]
    await db_session.execute(
        update(TenantConfiguration)
        .where(TenantConfiguration.tenant_id == SYSTEM_TENANT_ID)
        .values(sherlock_instructions=sentinel)
    )
    await db_session.commit()

    block = await load_instructions(
        'voice-rx', tenant_id=SYSTEM_TENANT_ID, db=db_session,
    )

    # Both present.
    assert 'one decimal place' in block.lower()
    assert sentinel in block
    # Order: app default first, tenant override later.
    assert block.index('one decimal place') < block.index(sentinel)
    # Tenant override carries its visible heading.
    assert '## Tenant overrides' in block


@pytest.mark.asyncio
async def test_prompt_skips_heading_when_block_is_empty(
    db_session, reset_tenant_override,
) -> None:
    prompt = build_data_specialist_prompt(
        app_id='voice-rx',
        schema_context={'agg_evaluation_run': {}},
        allowed_tables=['agg_evaluation_run'],
        column_role_hints=['agg_evaluation_run.status is dimension'],
        exemplars=[],
        max_rows=200,
        grounding_header=None,
        instructions_block='',
    )
    assert 'INSTRUCTIONS (residual rules' not in prompt


@pytest.mark.asyncio
async def test_prompt_renders_instructions_block(
    db_session, reset_tenant_override,
) -> None:
    block = await load_instructions(
        'voice-rx', tenant_id=SYSTEM_TENANT_ID, db=db_session,
    )
    prompt = build_data_specialist_prompt(
        app_id='voice-rx',
        schema_context={'agg_evaluation_run': {}},
        allowed_tables=['agg_evaluation_run'],
        column_role_hints=['agg_evaluation_run.status is dimension'],
        exemplars=[],
        max_rows=200,
        grounding_header=None,
        instructions_block=block,
    )
    assert 'BUSINESS SEMANTICS' in prompt
    assert 'one decimal place' in prompt.lower()


def _sample_data_prompt() -> str:
    return build_data_specialist_prompt(
        app_id='voice-rx',
        schema_context={'agg_evaluation_run': {}},
        allowed_tables=['agg_evaluation_run'],
        column_role_hints=['agg_evaluation_run.status is dimension'],
        exemplars=[],
        max_rows=200,
        grounding_header=None,
        instructions_block='',
    )


def test_data_prompt_keeps_submit_sql_contract_tokens() -> None:
    prompt = _sample_data_prompt()
    for token in (
        'output_columns',
        'declared_grain',
        'expected_row_bound',
        'chart_title',
        'prior_attempts',
        'retry_hint',
        'SpecialistResult',
        'submit_sql',
    ):
        assert token in prompt, f'missing contract token: {token}'


def test_data_prompt_drops_call_it_once_framing() -> None:
    prompt = _sample_data_prompt()
    assert 'Call it ONCE' not in prompt
    # Self-loop language is present instead.
    assert 'resubmit' in prompt or 'until it passes' in prompt


def test_data_prompt_static_output_contract_precedes_catalog() -> None:
    # Approved static-first reorder: the static OUTPUT_CONTRACT sits with the
    # other static prose, BEFORE the per-app catalog YAML / business semantics.
    prompt = _sample_data_prompt()
    assert prompt.index('TOOL CALL FORMAT') < prompt.index(
        'SCHEMA (logical column names accepted by the bouncer):'
    )


# ── synonyms authoring (P1-2) + no-drift audit ──────────────────────

from app.services.chat_engine.workbench_catalog import (  # noqa: E402
    _clear_catalog_cache_for_tests,
    load_workbench_catalog_strict,
)

_SYNONYMS_APPS = ('kaira-bot', 'voice-rx', 'inside-sales')


def _all_synonym_bearers(catalog):
    for table in catalog.tables.values():
        for col in (*table.dimensions, *table.time_dimensions, *table.facts):
            yield f'{table.name}.{col.name}', col.name, col.synonyms
        for metric in table.metrics:
            yield f'{table.name}::{metric.name}', metric.name, metric.synonyms


@pytest.mark.parametrize('app_id', _SYNONYMS_APPS)
def test_catalog_has_synonyms(app_id: str) -> None:
    _clear_catalog_cache_for_tests()
    catalog = load_workbench_catalog_strict(app_id)
    total = sum(len(syns) for _, _, syns in _all_synonym_bearers(catalog))
    assert total >= 1, f'{app_id}: catalog declares no synonyms'


@pytest.mark.parametrize('app_id', _SYNONYMS_APPS)
def test_synonyms_lowercase_no_self_or_internal_dup(app_id: str) -> None:
    _clear_catalog_cache_for_tests()
    catalog = load_workbench_catalog_strict(app_id)
    for owner, name, syns in _all_synonym_bearers(catalog):
        if not syns:
            continue
        for syn in syns:
            assert syn == syn.lower(), f'{owner}: non-lowercase synonym {syn!r}'
            assert syn.strip() == syn and syn.strip(), f'{owner}: padded/empty synonym {syn!r}'
        lowered = [s.lower() for s in syns]
        assert len(lowered) == len(set(lowered)), f'{owner}: internal duplicate in {syns!r}'
        own = {name.lower(), name.lower().replace('_', ' ')}
        assert not own.intersection(lowered), f'{owner}: synonym restates own name {syns!r}'


@pytest.mark.parametrize('app_id', _SYNONYMS_APPS)
def test_catalog_parses_and_cross_checks(app_id: str) -> None:
    # Synonyms are additive on the frozen LogicalColumn/Metric — the catalog
    # must still parse, cross-check, and keep its column count intact.
    _clear_catalog_cache_for_tests()
    catalog = load_workbench_catalog_strict(app_id)
    cols = sum(
        len(t.dimensions) + len(t.time_dimensions) + len(t.facts)
        for t in catalog.tables.values()
    )
    assert cols > 0


def test_catalog_synonyms_are_planner_facing_only() -> None:
    # No-drift: the curated synonyms surface lives on the catalog and reaches
    # the planner via catalog_vocabulary — never re-stitched into the SQL-shape
    # prompt projection, which has no synonyms key at all.
    from app.services.chat_engine.workbench_catalog import (
        catalog_vocabulary,
        workbench_to_prompt_inputs,
    )

    _clear_catalog_cache_for_tests()
    catalog = load_workbench_catalog_strict('inside-sales')
    vocab = catalog_vocabulary(catalog)
    assert any(entry['synonyms'] for entry in vocab), 'vocabulary carries no synonyms'

    schema_context, _allowed, _hints, _exemplars = workbench_to_prompt_inputs(catalog)
    for table_payload in schema_context['tables'].values():
        for col in table_payload['columns']:
            assert 'synonyms' not in col, (
                'synonyms drifted into the SQL-shape prompt projection; '
                'they belong only on the planner vocabulary'
            )
