"""Guard tests — authoring + cross-tenant prompt directives must persist.

These assert the surgical directives that make authoring proceed reliably
on a concrete edit-mode request, never claim the canvas is open/edited/
saved, and refuse cross-tenant asks. They guard against silent removal —
they do NOT prove runtime behavior (that is the live-consistency gate).
"""
from __future__ import annotations

import uuid

from app.services.sherlock_v3.authoring_specialist import _build_system_prompt
from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.sherlock_v3.query_synthesis_specialist import _PERSONALITY
from app.services.sherlock_v3.supervisor import _SUPERVISOR_PROMPT


def _authoring_prompt() -> str:
    snapshot = BuilderSnapshot(
        workflow_id=uuid.uuid4(),
        workflow_type='crm',
        app_id='inside-sales',
        definition={'nodes': [], 'edges': []},
        data_hash='deadbeef',
        view_mode='edit',
    )
    return _build_system_prompt(app_id='inside-sales', builder_context=snapshot)


def test_authoring_prompt_propose_only_never_claim_open_or_saved():
    prompt = _authoring_prompt()
    # propose-only / never-claim-open-or-saved directive
    assert 'NEVER claim the canvas is open, edited, applied, or saved' in prompt


def test_authoring_prompt_proceeds_on_concrete_edit_request():
    prompt = _authoring_prompt()
    # proceed-to-author directive: resolve + one apply_patch on a concrete ask
    assert (
        'When the request is concrete, proceed: resolve what you need\n'
        '   (`list_*` lookups) and emit ONE `apply_patch`'
    ) in prompt
    # ask only when a required value is genuinely missing/ambiguous
    assert 'ask ONE clarifying question only' in prompt
    assert 'when a required value is genuinely missing or ambiguous' in prompt


def test_planner_routes_concrete_edit_request_to_authoring():
    # planner must route a concrete edit-mode authoring ask to answerable
    assert (
        'When "authoring_specialist" is in AVAILABLE_TARGETS and the user\n'
        '    makes a concrete edit request, classify "answerable"'
    ) in _PERSONALITY


def test_cross_tenant_refusal_directive_present():
    # cross-tenant refusal lives in the planner (the classification owner)
    assert (
        'A request to act on ANOTHER tenant\'s data is "non_data"'
    ) in _PERSONALITY
