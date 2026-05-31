"""S1-P-A — structural guard for the trimmed supervisor prompt.

Asserts the load-bearing contract tokens survive the trim, the cut markers
(the three restated XML blocks + the hidden-mirror essay) are gone, the
hidden-mirror auto-translation hint is collapsed to one surviving mention,
the static prose precedes the first dynamic injection (cache-prefix safe),
and the ``.format()`` contract is intact.
"""
from __future__ import annotations

from app.services.sherlock_v3.supervisor import _SUPERVISOR_PROMPT


def test_supervisor_prompt_keeps_load_bearing_tokens() -> None:
    for token in (
        'SpecialistBrief',
        'SpecialistResult',
        'prior_attempts',
        'retry_hint',
        'MAX_ATTEMPTS',
        'query_synthesis_specialist',
        '{app_id}',
        '{available_tools_block}',
    ):
        assert token in _SUPERVISOR_PROMPT, f'missing load-bearing token: {token}'


def test_supervisor_prompt_keeps_output_format_rules() -> None:
    # markdown / no-ASCII / no-inline-evidence-UUID + authoring-proposes.
    assert 'Markdown' in _SUPERVISOR_PROMPT
    assert 'ASCII' in _SUPERVISOR_PROMPT
    assert 'Evidence ref' in _SUPERVISOR_PROMPT
    assert 'never claim' in _SUPERVISOR_PROMPT.lower()


def test_supervisor_prompt_drops_restated_xml_blocks() -> None:
    for marker in (
        '<instruction_priority>',
        '<tool_persistence_rules>',
        '<output_contract>',
    ):
        assert marker not in _SUPERVISOR_PROMPT, f'cut marker still present: {marker}'


def test_supervisor_prompt_collapses_hidden_mirror_essay() -> None:
    # D3: keep the auto-translation hint (fact_lead_activity), drop the essay.
    assert 'fact_lead_activity' in _SUPERVISOR_PROMPT
    # The 12-line essay header is gone.
    assert '# Hidden-mirror recovery' not in _SUPERVISOR_PROMPT
    # Collapsed to a single mention of the raw mirror table.
    assert _SUPERVISOR_PROMPT.count('crm_call_record') <= 1


def test_supervisor_prompt_static_first() -> None:
    # Static prose (the role/personality framing) precedes the first dynamic
    # injection so a future cache-prefix step has a stable anchor.
    assert _SUPERVISOR_PROMPT.index('Role:') < _SUPERVISOR_PROMPT.index('{app_id}')
    assert _SUPERVISOR_PROMPT.index('Role:') < _SUPERVISOR_PROMPT.index('{available_tools_block}')


def test_supervisor_prompt_format_contract_intact() -> None:
    rendered = _SUPERVISOR_PROMPT.format(app_id='voice-rx', available_tools_block='X')
    assert '{app_id}' not in rendered
    assert '{available_tools_block}' not in rendered
    assert 'voice-rx' in rendered
