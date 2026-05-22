"""BLOCKER B1 — resolve_source enriches static jsonb_keys on the run path.

The API layer used to be the only place that introspected JSONB keys; the
run path got the static catalog entry with ``jsonb_keys=[]`` and the compiler
emitted bare ``src.{key}`` → Postgres ``UndefinedColumn``. These tests pin the
contract: ``resolve_source`` returns a fully-resolved static source with
``jsonb_keys`` populated from one shared introspection, so the compiler routes
JSONB keys through ``src.raw_payload->>'key'`` and a real run does not crash.

Live-DB tests run against ``analytics.crm_lead_record`` (seeded inside-sales
data carries real JSONB keys like ``age_group`` / ``mql_score``).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.orchestration.nodes._cohort_query_compiler import (
    CohortQueryConfig,
    compile_cohort_query,
)
from app.services.orchestration.source_catalog import CohortSource, resolve_source


# Real seeded inside-sales CRM tenant/app/user (verified against the docker DB).
_CRM_TENANT_ID = uuid.UUID("af2fcf2b-40a7-4b1a-8fb1-6da0bed73383")
_CRM_APP_ID = "inside-sales"
_CRM_USER_ID = uuid.UUID("44a3afdf-78f8-4789-9f1f-96184359439a")
# A JSONB key that lives inside raw_payload (regex-safe) and is NOT a real column.
_CRM_JSONB_KEY = "age_group"


@pytest.mark.asyncio
async def test_resolve_source_static_populates_jsonb_keys(db_session):
    """A static source resolved with app context carries non-empty jsonb_keys."""
    resolved = await resolve_source(
        "crm.lead_record",
        db=db_session,
        tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID,
    )
    assert isinstance(resolved, CohortSource)
    assert resolved.jsonb_keys, "static source must be enriched with live jsonb_keys"
    assert _CRM_JSONB_KEY in resolved.jsonb_keys
    # Real columns must NOT show up as jsonb_keys.
    assert "city" not in resolved.jsonb_keys
    assert "lead_id" not in resolved.jsonb_keys


@pytest.mark.asyncio
async def test_resolve_source_static_jsonb_key_compiles_to_raw_payload(db_session):
    """End-to-end: a filter on a JSONB key compiles to src.raw_payload->>'key'."""
    resolved = await resolve_source(
        "crm.lead_record",
        db=db_session,
        tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID,
    )
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        filters=[{"column": _CRM_JSONB_KEY, "op": "eq", "value": "x"}],
        payload_fields=["city", _CRM_JSONB_KEY],
    )
    sql, params = compile_cohort_query(
        cfg,
        run_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID,
        next_node_id="n1",
        resolved_source=resolved,
    )
    assert f"src.raw_payload->>'{_CRM_JSONB_KEY}' = :filter_0" in sql
    assert f"src.{_CRM_JSONB_KEY} =" not in sql
    # Real column stays bare.
    assert "'city', src.city" in sql
    assert f"'{_CRM_JSONB_KEY}', src.raw_payload->>'{_CRM_JSONB_KEY}'" in sql


@pytest.mark.asyncio
async def test_saved_mode_query_config_jsonb_key_compiles_to_raw_payload(db_session):
    """Saved mode: a version row's JSONB-key filter resolves through the same
    enrichment as inline mode (both flow through resolve_source +
    _materialize_cohort), so the saved path also emits raw_payload->>'key'."""
    from app.models.orchestration import CohortDefinition, CohortDefinitionVersion
    from app.services.orchestration.nodes.source_cohort import _query_config_from_version

    cd_id = uuid.uuid4()
    db_session.add(CohortDefinition(
        id=cd_id, tenant_id=_CRM_TENANT_ID, app_id=_CRM_APP_ID,
        slug=f"b1-saved-{uuid.uuid4().hex[:8]}",
        name="b1 saved", created_by=_CRM_USER_ID,
    ))
    await db_session.flush()
    version = CohortDefinitionVersion(
        id=uuid.uuid4(), tenant_id=_CRM_TENANT_ID, app_id=_CRM_APP_ID,
        cohort_definition_id=cd_id, version=1, source_ref="crm.lead_record",
        filters=[{"column": _CRM_JSONB_KEY, "op": "eq", "value": "x"}],
        payload_fields=[_CRM_JSONB_KEY], status="published",
    )
    db_session.add(version)
    await db_session.flush()

    query_config = _query_config_from_version(version)
    resolved = await resolve_source(
        version.source_ref, db=db_session,
        tenant_id=_CRM_TENANT_ID, app_id=_CRM_APP_ID,
    )
    sql, _params = compile_cohort_query(
        query_config,
        run_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID,
        next_node_id="n1",
        resolved_source=resolved,
    )
    assert f"src.raw_payload->>'{_CRM_JSONB_KEY}' = :filter_0" in sql
    assert f"'{_CRM_JSONB_KEY}', src.raw_payload->>'{_CRM_JSONB_KEY}'" in sql


@pytest.mark.asyncio
async def test_compiled_jsonb_filter_runs_without_undefined_column(db_session):
    """Acceptance gate: the compiled SQL executes against the live DB with no
    UndefinedColumn when filtering on a JSONB key. Inserts into a throwaway run
    id; the savepoint fixture rolls it back."""
    resolved = await resolve_source(
        "crm.lead_record",
        db=db_session,
        tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID,
    )
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        filters=[{"column": _CRM_JSONB_KEY, "op": "eq", "value": "__no_match__"}],
        payload_fields=[_CRM_JSONB_KEY, "city"],
    )
    # Seed a workflow + version + run so the INSERT-from-SELECT satisfies FKs.
    from app.models.orchestration import Workflow, WorkflowRun, WorkflowVersion

    wf_id = uuid.uuid4()
    wfv_id = uuid.uuid4()
    run_id = uuid.uuid4()
    db_session.add(Workflow(
        id=wf_id, tenant_id=_CRM_TENANT_ID, app_id=_CRM_APP_ID,
        workflow_type="crm", slug=f"b1-{uuid.uuid4().hex[:8]}",
        name="b1-smoke", created_by=_CRM_USER_ID,
    ))
    await db_session.flush()
    db_session.add(WorkflowVersion(
        id=wfv_id, workflow_id=wf_id, tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID, version=1,
        definition={"nodes": [], "edges": []}, status="published",
    ))
    await db_session.flush()
    db_session.add(WorkflowRun(
        id=run_id, workflow_id=wf_id, workflow_version_id=wfv_id,
        tenant_id=_CRM_TENANT_ID, app_id=_CRM_APP_ID,
        triggered_by="manual", triggered_by_user_id=_CRM_USER_ID,
        status="running",
    ))
    await db_session.flush()

    sql, params = compile_cohort_query(
        cfg,
        run_id=run_id,
        workflow_id=wf_id,
        workflow_version_id=wfv_id,
        tenant_id=_CRM_TENANT_ID,
        app_id=_CRM_APP_ID,
        next_node_id="n1",
        resolved_source=resolved,
    )
    # The acceptance assertion: no UndefinedColumn raised on execute.
    result = await db_session.execute(text(sql), params)
    rows = result.all()
    # The filter value matches nothing, so an empty set is the expected (and
    # safe) outcome — what matters is the query ran.
    assert isinstance(rows, list)
