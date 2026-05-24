"""upstream-variables resolver — service + route tests.

The resolver walks a posted graph upstream from a target node and reports the
payload variables available there. Source-field discovery reuses the live
source catalog (``introspect_static_schema_descriptor`` / ``resolve_source``),
``CohortDefinitionVersion.payload_fields`` and a node's ``output_schema`` —
no real recipient row is ever fetched.

Source taxonomy (grouping key on each field):
  - ``cohort``  — real columns projected by a source.cohort node
  - ``static``  — raw_payload JSONB keys projected by a source.cohort node
  - ``dataset`` — columns of a source.dataset version (carry a sampleValue)
  - ``step``    — fields produced by an earlier node (llm.extract output,
                  dispatch emits)

Live-DB tests use the ``db_session`` fixture (local docker postgres). The
introspection real-column branch reads information_schema; the JSONB branch
reads tenant+app-scoped rows.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.orchestration import (
    CohortDataset,
    CohortDatasetVersion,
    CohortDefinition,
    CohortDefinitionVersion,
)
from app.models.tenant import Tenant
from app.schemas.orchestration import (
    ResolveUpstreamVariablesResponse,
    UpstreamField,
    WorkflowDefinitionEdge,
    WorkflowDefinitionNode,
)

APP_ID = "inside-sales"
CRM_REF = "crm.lead_record"


# ─── helpers ─────────────────────────────────────────────────────────────────


def _node(node_id: str, node_type: str, config: dict | None = None) -> WorkflowDefinitionNode:
    return WorkflowDefinitionNode(id=node_id, type=node_type, config=config or {})


def _edge(source: str, target: str) -> WorkflowDefinitionEdge:
    return WorkflowDefinitionEdge(id=f"{source}->{target}", source=source, target=target)


def _by_path(result: ResolveUpstreamVariablesResponse) -> dict[str, UpstreamField]:
    return {f.path: f for f in result.fields}


async def _make_tenant(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f"uv-{tenant_id.hex[:8]}",
        slug=f"uv-{tenant_id.hex[:8]}",
        is_active=True,
    ))
    await db_session.flush()
    return tenant_id


async def _make_saved_cohort_version(
    db_session, *, tenant_id: uuid.UUID, payload_fields: list[str],
) -> uuid.UUID:
    definition = CohortDefinition(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=APP_ID,
        slug=f"c-{uuid.uuid4().hex[:8]}", name="Saved Cohort", created_by=SYSTEM_USER_ID,
    )
    db_session.add(definition)
    await db_session.flush()
    version = CohortDefinitionVersion(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=APP_ID,
        cohort_definition_id=definition.id, version=1,
        source_ref=CRM_REF, payload_fields=payload_fields, status="published",
    )
    db_session.add(version)
    await db_session.flush()
    return version.id


async def _make_dataset_version(
    db_session, *, tenant_id: uuid.UUID, columns: list[dict],
) -> uuid.UUID:
    dataset = CohortDataset(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=APP_ID,
        name=f"ds-{uuid.uuid4().hex[:8]}", created_by=SYSTEM_USER_ID,
    )
    db_session.add(dataset)
    await db_session.flush()
    version = CohortDatasetVersion(
        id=uuid.uuid4(), dataset_id=dataset.id, tenant_id=tenant_id,
        version_number=1, source_type="csv", row_count=3, id_strategy="uuid",
        schema_descriptor={"columns": columns, "row_count": 3},
        imported_by=SYSTEM_USER_ID,
    )
    db_session.add(version)
    await db_session.flush()
    return version.id


# ─── service: source-field resolution ────────────────────────────────────────


@pytest.mark.asyncio
async def test_inline_cohort_real_columns_resolve_as_cohort(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    nodes = [
        _node("src", "source.cohort", {
            "mode": "inline", "source_ref": CRM_REF,
            "payload_fields": ["first_name", "city"],
        }),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("src", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    fields = _by_path(result)
    assert "first_name" in fields and "city" in fields
    assert fields["first_name"].source == "cohort"
    assert fields["first_name"].source_node_id == "src"
    assert fields["first_name"].is_jsonb is False
    # cohort contributes typed blanks — no sample value.
    assert result.sample.get("first_name") is None
    assert result.unresolved == []


@pytest.mark.asyncio
async def test_saved_cohort_payload_fields_resolve(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    version_id = await _make_saved_cohort_version(
        db_session, tenant_id=tenant_id, payload_fields=["first_name", "last_name"],
    )
    nodes = [
        _node("src", "source.cohort", {
            "mode": "saved", "cohort_definition_version_id": str(version_id),
        }),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("src", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    fields = _by_path(result)
    assert "first_name" in fields and "last_name" in fields
    assert fields["last_name"].source == "cohort"


@pytest.mark.asyncio
async def test_cohort_jsonb_key_tagged_static(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    # Seed one CRM row so the JSONB-key introspection surfaces prospect_stage.
    await db_session.execute(
        text(
            "INSERT INTO analytics.crm_lead_record "
            "(id, lead_id, tenant_id, app_id, first_name, raw_payload) "
            "VALUES (:id, :lead, :t, :a, :fn, CAST(:rp AS jsonb))"
        ),
        {
            "id": str(uuid.uuid4()), "lead": f"L-{uuid.uuid4().hex[:8]}",
            "t": str(tenant_id), "a": APP_ID, "fn": "Asha",
            "rp": '{"prospect_stage": "active"}',
        },
    )
    await db_session.flush()

    nodes = [
        _node("src", "source.cohort", {
            "mode": "inline", "source_ref": CRM_REF,
            "payload_fields": ["first_name", "prospect_stage"],
        }),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("src", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    fields = _by_path(result)
    assert fields["prospect_stage"].source == "static"
    assert fields["prospect_stage"].is_jsonb is True
    assert fields["first_name"].source == "cohort"


@pytest.mark.asyncio
async def test_dataset_columns_carry_sample_value(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    version_id = await _make_dataset_version(
        db_session, tenant_id=tenant_id, columns=[
            {"name": "name", "type": "string", "sample_values": ["Asha", "Ravi"]},
            {"name": "age", "type": "number", "sample_values": [30, 41]},
        ],
    )
    nodes = [
        _node("src", "source.dataset", {"dataset_version_id": str(version_id)}),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("src", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    fields = _by_path(result)
    assert fields["name"].source == "dataset"
    assert fields["name"].type == "string"
    assert fields["name"].sample_value == "Asha"
    assert result.sample["name"] == "Asha"
    assert fields["age"].sample_value == 30


@pytest.mark.asyncio
async def test_earlier_llm_extract_outputs_are_namespaced(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    nodes = [
        _node("analyze", "llm.extract", {
            "output_namespace": "analysis",
            "output_schema": [
                {"key": "sentiment", "type": "enum"},
                {"key": "confidence", "type": "number"},
            ],
        }),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("analyze", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    fields = _by_path(result)
    assert "analysis.sentiment" in fields
    assert fields["analysis.sentiment"].source == "step"
    assert fields["analysis.sentiment"].type == "enum"
    assert fields["analysis.sentiment"].source_node_id == "analyze"
    assert "analysis.confidence" in fields


@pytest.mark.asyncio
async def test_llm_extract_without_namespace_uses_node_id(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    nodes = [
        _node("classify", "llm.extract", {
            "output_schema": [{"key": "topic", "type": "text"}],
        }),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("classify", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    assert "classify.topic" in _by_path(result)


@pytest.mark.asyncio
async def test_dispatch_emits_are_mapped_server_side(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    nodes = [
        _node("wa", "messaging.send_whatsapp_template", {}),
        _node("call", "voice.place_call", {}),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("wa", "ai"), _edge("call", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    paths = set(_by_path(result).keys())
    assert "steps.wa.wa_button_id" in paths
    assert "steps.wa.wa_reply_text" in paths
    assert "steps.call.voice_outcome" in paths


@pytest.mark.asyncio
async def test_multi_hop_through_filter_node(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    nodes = [
        _node("src", "source.cohort", {
            "mode": "inline", "source_ref": CRM_REF, "payload_fields": ["first_name"],
        }),
        _node("filter", "filter.eligibility", {}),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("src", "filter"), _edge("filter", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    assert "first_name" in _by_path(result)


@pytest.mark.asyncio
async def test_event_trigger_reports_unresolved(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    nodes = [
        _node("evt", "source.event_trigger", {}),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("evt", "ai")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="ai",
    )

    assert result.fields == []
    assert len(result.unresolved) == 1
    assert result.unresolved[0].node_id == "evt"
    assert result.unresolved[0].reason


@pytest.mark.asyncio
async def test_cross_tenant_saved_cohort_raises_not_found(db_session):
    from app.services.orchestration.upstream_variables import (
        UpstreamSourceNotFound,
        resolve_upstream_variables,
    )

    owner = await _make_tenant(db_session)
    other = await _make_tenant(db_session)
    version_id = await _make_saved_cohort_version(
        db_session, tenant_id=owner, payload_fields=["first_name"],
    )
    nodes = [
        _node("src", "source.cohort", {
            "mode": "saved", "cohort_definition_version_id": str(version_id),
        }),
        _node("ai", "llm.extract", {}),
    ]
    edges = [_edge("src", "ai")]

    with pytest.raises(UpstreamSourceNotFound):
        await resolve_upstream_variables(
            db_session, tenant_id=other, app_id=APP_ID, workflow_type="crm",
            nodes=nodes, edges=edges, target_node_id="ai",
        )


# ─── route ───────────────────────────────────────────────────────────────────


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _make_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=SYSTEM_USER_ID,
        tenant_id=tenant_id,
        email="upstream-vars@orchestration.local",
        role_id=uuid.uuid4(),
        is_owner=True,
        permissions=frozenset(),
        app_access=frozenset({"voice-rx", "kaira-bot", "inside-sales"}),
    )


def _override_auth(auth: AuthContext):
    fastapi_app.dependency_overrides[get_auth_context] = lambda: auth


@pytest_asyncio.fixture
async def route_tenant_id(db_session) -> uuid.UUID:
    return await _make_tenant(db_session)


@pytest_asyncio.fixture
async def client(db_session, route_tenant_id):
    _override_db(db_session)
    _override_auth(_make_auth(route_tenant_id))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


@pytest_asyncio.fixture
async def unauth_client(db_session):
    _override_db(db_session)
    fastapi_app.dependency_overrides.pop(get_auth_context, None)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


def _resolve_body(nodes: list[dict], edges: list[dict], target: str) -> dict:
    return {
        "appId": APP_ID,
        "workflowType": "crm",
        "nodes": nodes,
        "edges": edges,
        "targetNodeId": target,
    }


@pytest.mark.asyncio
async def test_route_requires_auth(unauth_client):
    r = await unauth_client.post(
        "/api/orchestration/nodes/upstream-variables",
        json=_resolve_body([], [], "ai"),
    )
    assert r.status_code in (401, 403), r.text


@pytest.mark.asyncio
async def test_route_returns_fields_for_saved_cohort_graph(client, db_session, route_tenant_id):
    version_id = await _make_saved_cohort_version(
        db_session, tenant_id=route_tenant_id, payload_fields=["first_name", "city"],
    )
    nodes = [
        {"id": "src", "type": "source.cohort", "config": {
            "mode": "saved", "cohort_definition_version_id": str(version_id)}},
        {"id": "ai", "type": "llm.extract", "config": {}},
    ]
    edges = [{"id": "e1", "source": "src", "target": "ai"}]

    r = await client.post(
        "/api/orchestration/nodes/upstream-variables",
        json=_resolve_body(nodes, edges, "ai"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    paths = {f["path"]: f for f in body["fields"]}
    assert "first_name" in paths
    assert paths["first_name"]["sourceNodeId"] == "src"
    assert paths["first_name"]["source"] == "cohort"
    assert "sample" in body and "unresolved" in body


@pytest.mark.asyncio
async def test_route_cross_tenant_dataset_returns_404(client, db_session, route_tenant_id):
    other = await _make_tenant(db_session)
    version_id = await _make_dataset_version(
        db_session, tenant_id=other, columns=[
            {"name": "name", "type": "string", "sample_values": ["x"]},
        ],
    )
    nodes = [
        {"id": "src", "type": "source.dataset", "config": {
            "dataset_version_id": str(version_id)}},
        {"id": "ai", "type": "llm.extract", "config": {}},
    ]
    edges = [{"id": "e1", "source": "src", "target": "ai"}]

    r = await client.post(
        "/api/orchestration/nodes/upstream-variables",
        json=_resolve_body(nodes, edges, "ai"),
    )
    assert r.status_code == 404, r.text
