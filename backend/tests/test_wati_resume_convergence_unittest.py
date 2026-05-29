"""WS4: WATI reply-resume converges onto the shared gated resume core.

A WhatsApp reply must wake a parked recipient ONLY through
``resume_waiting_on_event`` (the same gated core voice + inbound events use),
never an unconditional waiting->ready flip. Non-reply status events
(delivered / read / sent / failed) keep their record-only path.

Verbatim WATI webhook fixtures; no live WATI.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.orchestration.adapters import canonical
from app.services.orchestration.adapters import wati as wati_mod
from app.services.orchestration.adapters.wati import WatiAdapter
from app.services.orchestration.dispatch import event_resume


# ─── Verbatim WATI webhook fixtures ─────────────────────────────────────────

REPLY_BUTTON_FIXTURE = {
    "eventType": "sentMessageREPLIED_v2",
    "statusString": "Replied",
    "localMessageId": "d38f0c3a-e833-4725-a894-53a2b1dc1af6",
    "id": "640c8fd48b67615f886237b8",
    "whatsappMessageId": "gBEGkXmJQZVJAgkRHwjjZsITS6M",
    "replyContextId": "OLD_OUTBOUND_WA_MSG_ID",
    "waId": "919999999999",
    "buttonReply": {
        "payload": '{"ButtonIndex":0,"CarouselCardIndex":null,"BroadcastLinkId":"676a9b2e57150cedccdb7a17"}',
        "text": "Tell me more",
    },
}

MESSAGE_RECEIVED_TEXT_FIXTURE = {
    "eventType": "messageReceived",
    "localMessageId": "lm-text-1",
    "waId": "919999999999",
    "type": "text",
    "text": "Yes please",
}

DELIVERED_FIXTURE = {
    "eventType": "sentMessageDELIVERED_v2",
    "localMessageId": "lm-deliv-1",
    "waId": "919999999999",
    "whatsappMessageId": "WAMID_OUT_1",
}

READ_FIXTURE = {
    "eventType": "sentMessageREAD_v2",
    "localMessageId": "lm-read-1",
    "waId": "919999999999",
    "whatsappMessageId": "WAMID_OUT_1",
}


# ─── Minimal fakes ──────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount


class _RoutingSession:
    """Swallows every write; records nothing the routing test cares about."""

    def __init__(self, flip_rowcount: int = 1):
        self._flip_rowcount = flip_rowcount

    async def execute(self, *_a, **_k):
        return _FakeResult(rowcount=self._flip_rowcount)

    async def scalar(self, *_a, **_k):
        return None

    async def flush(self):
        return None


class _VersionSession:
    """Serves exactly the calls ``_resume_state`` makes: one ``scalar`` for the
    WorkflowVersion, then ``execute`` updates whose rowcount we track."""

    def __init__(self, version):
        self._version = version
        self.flip_count = 0

    async def scalar(self, *_a, **_k):
        return self._version

    async def execute(self, *_a, **_k):
        # Every update through here would flip/merge state in production.
        self.flip_count += 1
        return _FakeResult(rowcount=1)

    async def flush(self):
        return None


def _make_parent():
    return SimpleNamespace(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        recipient_id="R1",
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        node_step_id=uuid.uuid4(),
        provider_correlation_id="lm-1",
        provider_reply_ref=None,
        payload={"contact": "+919999999999"},
    )


def _state_for(parent, *, version_id):
    return SimpleNamespace(
        run_id=parent.run_id,
        recipient_id=parent.recipient_id,
        current_node_id="wait-1",
        workflow_version_id=version_id,
    )


def _version_with_wait(*, mode: str, event_name: str | None, event_match=None):
    config: dict = {
        "mode": mode,
        "event_name": event_name,
        "event_match": event_match,
        "timeout_hours": 24,
    }
    # event / event_or_timeout modes require a correlation block (path-A wati
    # resume passes match_correlation=False, so it is not enforced at resume).
    if mode in ("event", "event_or_timeout"):
        config["correlation"] = {"recipient_id_field": "recipient_id"}
    definition = {
        "nodes": [{"id": "wait-1", "type": "logic.wait", "config": config}],
        "edges": [],
    }
    return SimpleNamespace(id=uuid.uuid4(), definition=definition)


# ─── (1) A reply routes through the shared gated core ───────────────────────


@pytest.mark.asyncio
async def test_reply_routes_through_shared_resume_core(monkeypatch):
    parent = _make_parent()
    calls: list[dict] = []

    async def _spy_resume(db, **kwargs):
        calls.append(kwargs)
        return True

    # Reply path must call the shared core, not an inline flip.
    monkeypatch.setattr(wati_mod, "resume_waiting_on_event", _spy_resume)

    async def _fake_find_parent(self, db, *, tenant_id, payload):
        return parent, "wait-1"

    monkeypatch.setattr(WatiAdapter, "_find_parent", _fake_find_parent)

    await WatiAdapter().handle_webhook(
        _RoutingSession(), tenant_id=uuid.uuid4(), app_id="kaira-bot",
        payload=REPLY_BUTTON_FIXTURE,
    )

    assert len(calls) == 1, "reply must invoke the shared resume_waiting_on_event exactly once"
    kw = calls[0]
    assert kw["run_id"] == parent.run_id
    assert kw["recipient_id"] == parent.recipient_id
    # The canonical messaging reply event is what the wait is gated on.
    assert canonical.MESSAGING_REPLY_EVENT in set(kw["event_names"])


@pytest.mark.asyncio
async def test_message_received_reply_also_routes_through_core(monkeypatch):
    parent = _make_parent()
    calls: list[dict] = []

    async def _spy_resume(db, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(wati_mod, "resume_waiting_on_event", _spy_resume)

    async def _fake_find_parent(self, db, *, tenant_id, payload):
        return parent, "wait-1"

    monkeypatch.setattr(WatiAdapter, "_find_parent", _fake_find_parent)

    await WatiAdapter().handle_webhook(
        _RoutingSession(), tenant_id=uuid.uuid4(), app_id="kaira-bot",
        payload=MESSAGE_RECEIVED_TEXT_FIXTURE,
    )

    assert len(calls) == 1


# ─── (3) Non-reply status events just record — never resume ─────────────────


@pytest.mark.parametrize("fixture", [DELIVERED_FIXTURE, READ_FIXTURE])
@pytest.mark.asyncio
async def test_status_events_do_not_resume(monkeypatch, fixture):
    parent = _make_parent()
    calls: list[dict] = []

    async def _spy_resume(db, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(wati_mod, "resume_waiting_on_event", _spy_resume)

    async def _fake_find_parent(self, db, *, tenant_id, payload):
        return parent, "wait-1"

    monkeypatch.setattr(WatiAdapter, "_find_parent", _fake_find_parent)

    await WatiAdapter().handle_webhook(
        _RoutingSession(), tenant_id=uuid.uuid4(), app_id="kaira-bot",
        payload=fixture,
    )

    assert calls == [], "delivered / read must record only — never wake a wait"


# ─── (2) The shared core does NOT wake a non-matching wait ──────────────────
# These exercise the REAL gate with the messaging reply event, proving a
# WhatsApp reply cannot wrongly wake a voice / CRM / wrong-name / wrong-match wait.


@pytest.mark.asyncio
async def test_core_wakes_matching_messaging_wait(monkeypatch):
    parent = _make_parent()
    version = _version_with_wait(mode="event", event_name=canonical.MESSAGING_REPLY_EVENT)
    state = _state_for(parent, version_id=version.id)
    db = _VersionSession(version)

    enqueued: list[dict] = []

    async def _spy_enqueue(_db, **kwargs):
        enqueued.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(
        "app.services.orchestration.dispatch.resume_enqueue.enqueue_resume_for_recipient",
        _spy_enqueue,
    )

    resumed = await event_resume._resume_state(
        db, state=state,
        event_names={canonical.MESSAGING_REPLY_EVENT},
        payload={"wa_reply_text": "Tell me more"},
        reason="ready:wati:reply",
    )
    assert resumed is True
    assert db.flip_count >= 1
    assert len(enqueued) == 1
    assert enqueued[0]["recipient_id"] == parent.recipient_id


@pytest.mark.asyncio
async def test_reply_does_not_wake_voice_wait():
    parent = _make_parent()
    # A voice wait — event_name is a voice outcome, not the messaging reply event.
    version = _version_with_wait(mode="event", event_name="voice.answered")
    state = _state_for(parent, version_id=version.id)
    db = _VersionSession(version)

    resumed = await event_resume._resume_state(
        db, state=state,
        event_names={canonical.MESSAGING_REPLY_EVENT},
        payload={"wa_reply_text": "hi"},
        reason="ready:wati:reply",
    )
    assert resumed is False
    assert db.flip_count == 0


@pytest.mark.asyncio
async def test_reply_does_not_wake_crm_wait():
    parent = _make_parent()
    version = _version_with_wait(mode="event", event_name="crm.lead_updated")
    state = _state_for(parent, version_id=version.id)
    db = _VersionSession(version)

    resumed = await event_resume._resume_state(
        db, state=state,
        event_names={canonical.MESSAGING_REPLY_EVENT},
        payload={"wa_reply_text": "hi"},
        reason="ready:wati:reply",
    )
    assert resumed is False
    assert db.flip_count == 0


@pytest.mark.asyncio
async def test_reply_does_not_wake_non_event_mode_wait():
    parent = _make_parent()
    # A pure-timer wait must never be woken by a reply.
    version = _version_with_wait(mode="duration", event_name=None)
    # duration-mode config also needs duration fields; rebuild minimally.
    version.definition["nodes"][0]["config"] = {
        "mode": "duration", "duration_value": 1, "duration_unit": "hours",
    }
    state = _state_for(parent, version_id=version.id)
    db = _VersionSession(version)

    resumed = await event_resume._resume_state(
        db, state=state,
        event_names={canonical.MESSAGING_REPLY_EVENT},
        payload={"wa_reply_text": "hi"},
        reason="ready:wati:reply",
    )
    assert resumed is False
    assert db.flip_count == 0


@pytest.mark.asyncio
async def test_reply_does_not_wake_wait_with_unsatisfied_event_match():
    parent = _make_parent()
    version = _version_with_wait(
        mode="event_or_timeout",
        event_name=canonical.MESSAGING_REPLY_EVENT,
        event_match={"field": "wa_button_id", "op": "eq", "value": "1"},
    )
    state = _state_for(parent, version_id=version.id)
    db = _VersionSession(version)

    # Reply payload carries button 0, not 1 — the predicate must reject.
    resumed = await event_resume._resume_state(
        db, state=state,
        event_names={canonical.MESSAGING_REPLY_EVENT},
        payload={"wa_button_id": "0"},
        reason="ready:wati:reply",
    )
    assert resumed is False
    assert db.flip_count == 0
