"""WS3 — upstream resolver surfaces produced EVENTS + OUTCOME ENUMS; publish
rejects a logic.wait whose event_name is not an upstream-produced name.

The resolver now reports, per dispatch producer upstream of a target node:
  - OUTCOME ENUMS as canonical + providerLabel pairs (voice: answered/bolna_answered,
    no_answer/bolna_rnr, failed/bolna_failed; messaging: delivered/wa_delivered,
    read/wa_read, replied/<messaging.replied>), tagged with the producing node id
    and its resolved provider.
  - EVENT names a logic.wait downstream can resume on (voice.answered/…/voice.completed,
    messaging.replied).

The provider is resolved from the producer node's connection_id against the
tenant-scoped ProviderConnection row — cross-tenant stays read-only + 404.

No live external API: vendor outcome/event vocabularies come from the adapters'
existing canonical<->raw maps, asserted against verbatim values.
"""
from __future__ import annotations

import uuid

import pytest

from app.constants import SYSTEM_USER_ID
from app.models.provider_connection import ProviderConnection
from app.models.tenant import Tenant
from app.schemas.orchestration import WorkflowDefinitionEdge, WorkflowDefinitionNode
from app.services.orchestration.connections import crypto

APP_ID = "inside-sales"


def _node(node_id: str, node_type: str, config: dict | None = None) -> WorkflowDefinitionNode:
    return WorkflowDefinitionNode(id=node_id, type=node_type, config=config or {})


def _edge(source: str, target: str) -> WorkflowDefinitionEdge:
    return WorkflowDefinitionEdge(id=f"{source}->{target}", source=source, target=target)


async def _make_tenant(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id, name=f"wo-{tenant_id.hex[:8]}", slug=f"wo-{tenant_id.hex[:8]}",
        is_active=True,
    ))
    await db_session.flush()
    return tenant_id


async def _add_connection(db_session, *, tenant_id, provider) -> uuid.UUID:
    if provider == "wati":
        config = {"base_url": "https://w", "wati_tenant_id": "1", "api_token": "t"}
    elif provider == "bolna":
        config = {"api_key": "k", "base_url": "https://api.bolna.ai", "from_phone": "+91"}
    else:
        config = {"api_key": "k"}
    cid = uuid.uuid4()
    db_session.add(ProviderConnection(
        id=cid, tenant_id=tenant_id, app_id=APP_ID, provider=provider,
        name=f"{provider}-{cid.hex[:8]}", config_encrypted=crypto.encrypt(config),
        active=True, created_by=SYSTEM_USER_ID,
    ))
    await db_session.flush()
    return cid


def _outcomes_by_canonical(result):
    return {o.canonical: o for o in result.outcome_enums}


@pytest.mark.asyncio
async def test_voice_outcome_enums_and_events_surface(db_session):
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    conn_id = await _add_connection(db_session, tenant_id=tenant_id, provider="bolna")
    nodes = [
        _node("call", "voice.place_call", {"connection_id": str(conn_id)}),
        _node("wait", "logic.wait", {}),
    ]
    edges = [_edge("call", "wait")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="wait",
    )

    by_canon = _outcomes_by_canonical(result)
    assert by_canon["answered"].provider_label == "bolna_answered"
    assert by_canon["no_answer"].provider_label == "bolna_rnr"
    assert by_canon["failed"].provider_label == "bolna_failed"
    for o in by_canon.values():
        assert o.source_node_id == "call"
        assert o.provider == "bolna"

    event_names = {e.event_name for e in result.events}
    assert {"voice.answered", "voice.no_answer", "voice.failed", "voice.completed"} <= event_names
    assert all(e.source_node_id == "call" and e.provider == "bolna" for e in result.events)


@pytest.mark.asyncio
async def test_messaging_outcome_enums_and_reply_event_surface(db_session):
    from app.services.orchestration.adapters.canonical import MESSAGING_REPLY_EVENT
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    conn_id = await _add_connection(db_session, tenant_id=tenant_id, provider="wati")
    nodes = [
        _node("wa", "messaging.send_whatsapp_template", {"connection_id": str(conn_id)}),
        _node("wait", "logic.wait", {}),
    ]
    edges = [_edge("wa", "wait")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="wait",
    )

    by_canon = _outcomes_by_canonical(result)
    assert by_canon["delivered"].provider_label == "wa_delivered"
    assert by_canon["read"].provider_label == "wa_read"
    assert by_canon["replied"].provider_label == "wa_replied"
    for o in by_canon.values():
        assert o.source_node_id == "wa" and o.provider == "wati"

    event_names = {e.event_name for e in result.events}
    assert MESSAGING_REPLY_EVENT in event_names


@pytest.mark.asyncio
async def test_messaging_producer_without_inbound_surfaces_nothing(db_session):
    # AiSensy is a registered messaging adapter with no inbound support
    # (normalize_webhook raises, webhook returns 503). It must NOT surface a
    # fabricated WATI vocabulary — the resolver dispatches on the resolved
    # adapter, not a hardcoded vendor table.
    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    conn_id = await _add_connection(db_session, tenant_id=tenant_id, provider="aisensy")
    nodes = [
        _node("wa", "messaging.send_whatsapp_template", {"connection_id": str(conn_id)}),
        _node("wait", "logic.wait", {}),
    ]
    edges = [_edge("wa", "wait")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="wait",
    )

    assert result.outcome_enums == []
    assert result.events == []


@pytest.mark.asyncio
async def test_deactivated_connection_surfaces_unresolved(db_session):
    # A producer wired to an existing-but-deactivated connection surfaces an
    # unresolved entry (not silently nothing), so the builder can explain why.
    from sqlalchemy import update as _sa_update

    from app.services.orchestration.upstream_variables import resolve_upstream_variables

    tenant_id = await _make_tenant(db_session)
    conn_id = await _add_connection(db_session, tenant_id=tenant_id, provider="bolna")
    await db_session.execute(
        _sa_update(ProviderConnection)
        .where(ProviderConnection.id == conn_id)
        .values(active=False)
    )
    await db_session.flush()
    nodes = [
        _node("call", "voice.place_call", {"connection_id": str(conn_id)}),
        _node("wait", "logic.wait", {}),
    ]
    edges = [_edge("call", "wait")]

    result = await resolve_upstream_variables(
        db_session, tenant_id=tenant_id, app_id=APP_ID, workflow_type="crm",
        nodes=nodes, edges=edges, target_node_id="wait",
    )

    assert result.outcome_enums == []
    assert result.events == []
    assert any(u.node_id == "call" for u in result.unresolved)


@pytest.mark.asyncio
async def test_cross_tenant_connection_stays_not_found(db_session):
    from app.services.orchestration.upstream_variables import (
        UpstreamSourceNotFound,
        resolve_upstream_variables,
    )

    owner = await _make_tenant(db_session)
    other = await _make_tenant(db_session)
    conn_id = await _add_connection(db_session, tenant_id=owner, provider="bolna")
    nodes = [
        _node("call", "voice.place_call", {"connection_id": str(conn_id)}),
        _node("wait", "logic.wait", {}),
    ]
    edges = [_edge("call", "wait")]

    with pytest.raises(UpstreamSourceNotFound):
        await resolve_upstream_variables(
            db_session, tenant_id=other, app_id=APP_ID, workflow_type="crm",
            nodes=nodes, edges=edges, target_node_id="wait",
        )


# ─── publish-time validation ──────────────────────────────────────────────────


def _wait_event_definition(event_name: str) -> dict:
    return {
        "nodes": [
            {"id": "src", "type": "source.cohort", "config": {
                "mode": "inline", "source_ref": "crm.lead_record",
                "payload_fields": ["first_name"],
            }},
            {"id": "call", "type": "voice.place_call", "config": {
                "connection_id": str(uuid.uuid4()),
                "agent_id": "agent-1",
                "phone_field": "phone",
            }},
            {"id": "wait", "type": "logic.wait", "config": {
                "mode": "event_or_timeout",
                "event_name": event_name,
                "correlation": {"recipient_id_field": "recipient_id"},
                "timeout_hours": 1.0,
            }},
            {"id": "done", "type": "sink.complete", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "src", "target": "call", "output_id": "default"},
            {"id": "e2", "source": "call", "target": "wait", "output_id": "success"},
            {"id": "e3", "source": "wait", "target": "done", "output_id": "event"},
            {"id": "e4", "source": "wait", "target": "done", "output_id": "timeout"},
        ],
    }


def _messaging_wait_event_definition(event_name: str) -> dict:
    # Messaging-only workflow: the only upstream producer is a WhatsApp send,
    # so a voice event name must NOT pass publish here.
    return {
        "nodes": [
            {"id": "src", "type": "source.cohort", "config": {
                "mode": "inline", "source_ref": "crm.lead_record",
                "payload_fields": ["first_name"],
            }},
            {"id": "wa", "type": "messaging.send_whatsapp_template", "config": {
                "connection_id": str(uuid.uuid4()),
                "template_name": "welcome",
                "phone_field": "phone",
            }},
            {"id": "wait", "type": "logic.wait", "config": {
                "mode": "event_or_timeout",
                "event_name": event_name,
                "correlation": {"recipient_id_field": "recipient_id"},
                "timeout_hours": 1.0,
            }},
            {"id": "done", "type": "sink.complete", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "src", "target": "wa", "output_id": "default"},
            {"id": "e2", "source": "wa", "target": "wait", "output_id": "success"},
            {"id": "e3", "source": "wait", "target": "done", "output_id": "event"},
            {"id": "e4", "source": "wait", "target": "done", "output_id": "timeout"},
        ],
    }


def test_publish_rejects_voice_event_name_in_messaging_only_workflow():
    from app.services.orchestration.definition_validator import (
        DefinitionValidationError,
        validate_definition,
    )

    # voice.answered is a real produced name globally, but no voice node is
    # upstream of this wait — publish must reject it as not produced upstream.
    definition = _messaging_wait_event_definition("voice.answered")
    with pytest.raises(DefinitionValidationError) as exc:
        validate_definition(definition, workflow_type="crm", mode="publish")
    messages = " ".join(e["message"] for e in exc.value.errors if e["message"])
    assert "voice.answered" in messages


def test_publish_accepts_messaging_event_name_in_messaging_workflow():
    from app.services.orchestration.adapters.canonical import MESSAGING_REPLY_EVENT
    from app.services.orchestration.definition_validator import (
        DefinitionValidationError,
        validate_definition,
    )

    definition = _messaging_wait_event_definition(MESSAGING_REPLY_EVENT)
    try:
        validate_definition(definition, workflow_type="crm", mode="publish")
    except DefinitionValidationError as exc:
        msgs = " ".join(e["message"] for e in exc.errors if e["message"])
        assert MESSAGING_REPLY_EVENT not in msgs, f"known event wrongly rejected: {msgs}"


def test_publish_rejects_unknown_wait_event_name():
    from app.services.orchestration.definition_validator import (
        DefinitionValidationError,
        validate_definition,
    )

    definition = _wait_event_definition("totally.made.up.event")
    with pytest.raises(DefinitionValidationError) as exc:
        validate_definition(definition, workflow_type="crm", mode="publish")
    messages = " ".join(e["message"] for e in exc.value.errors if e["message"])
    assert "totally.made.up.event" in messages


def test_publish_accepts_known_wait_event_name():
    from app.services.orchestration.definition_validator import (
        DefinitionValidationError,
        validate_definition,
    )

    definition = _wait_event_definition("voice.answered")
    try:
        validate_definition(definition, workflow_type="crm", mode="publish")
    except DefinitionValidationError as exc:
        msgs = " ".join(e["message"] for e in exc.errors if e["message"])
        assert "voice.answered" not in msgs, f"known event wrongly rejected: {msgs}"


def test_draft_tolerates_unknown_legacy_event_name():
    from app.services.orchestration.definition_validator import (
        DefinitionValidationError,
        validate_definition,
    )

    definition = _wait_event_definition("legacy.unknown.event")
    try:
        validate_definition(definition, workflow_type="crm", mode="draft")
    except DefinitionValidationError as exc:
        msgs = " ".join(e["message"] for e in exc.errors if e["message"])
        assert "legacy.unknown.event" not in msgs, (
            f"draft must tolerate unknown event name: {msgs}"
        )
