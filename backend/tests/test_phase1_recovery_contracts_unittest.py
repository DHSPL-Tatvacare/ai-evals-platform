"""Phase 1 (Sherlock hardening) — generic recovery + state_delta contracts.

Covers the additive-and-optional contracts pinned in plan §42-107:

- ``ToolEnvelopeModel`` accepts + round-trips ``recovery`` and ``state_delta``
- envelopes without the new fields serialize byte-identically
- ``apply_state_delta`` merges each sub-field into the scratchpad
  deterministically, never clobbering unrelated state
- ``build_recovery_context`` / ``render_recovery_context_block`` surface
  the compact prior-failure + open-threads block the outer prompt reads
- the base system prompt carries the recovery/clarification policy
- ``render_recovery_semantics`` / ``{{recovery_semantics}}`` render the
  generic blurb once per tool without replacing pack reason_codes
- ``_update_scratchpad`` applies a pack-emitted ``state_delta`` end-to-end
"""
from __future__ import annotations

import json
import unittest

from app.services.chat_engine.artifact import (
    ToolEnvelopeModel,
    ToolRecoveryModel,
    ToolStateDeltaModel,
    build_envelope,
    error_envelope,
)
from app.services.report_builder import scratchpad_state
from app.services.report_builder.scratchpad_state import (
    apply_state_delta,
    apply_tool_recovery,
    build_recovery_context,
    confirmed_constraint_values,
    default_scratchpad,
    grounded_ref_values,
    render_recovery_context_block,
    resolve_open_thread,
)


# ---------------------------------------------------------------------------
# Envelope contract
# ---------------------------------------------------------------------------


class EnvelopeRecoveryStateDeltaTests(unittest.TestCase):
    def test_envelope_accepts_recovery_and_state_delta(self):
        env = build_envelope(
            status='partial',
            summary='empty slice',
            kind='read',
            capability='analytics',
            reason_code='CG_EMPTY',
            recovery={'recoverable': True, 'failure_kind': 'empty'},
            state_delta={
                'confirmed_constraints': [
                    {
                        'key': 'run_id',
                        'value': 'abc123',
                        'provenance': 'user_explicit',
                        'source_tool': 'data_query',
                    },
                ],
                'grounded_refs': [
                    {
                        'kind': 'run',
                        'key': 'run_id',
                        'value': 'abc123',
                        'provenance': 'resolver_derived',
                    },
                ],
                'open_threads': [
                    {
                        'kind': 'clarify',
                        'key': 'time_window',
                        'message': 'Which time window did you mean?',
                    },
                ],
                'last_result': {
                    'kind': 'empty',
                    'artifact_type': 'chart',
                    'row_count': 0,
                    'reason_code': 'CG_EMPTY',
                },
                'failure_record': {
                    'reason_code': 'CG_EMPTY',
                    'failure_kind': 'empty',
                    'recoverable': True,
                    'summary': 'empty slice',
                },
            },
        )
        self.assertIsInstance(env.recovery, ToolRecoveryModel)
        self.assertIsInstance(env.state_delta, ToolStateDeltaModel)
        assert env.recovery is not None  # narrow for type-checker
        self.assertTrue(env.recovery.recoverable)
        self.assertEqual(env.recovery.failure_kind, 'empty')

    def test_envelope_round_trips_through_dict(self):
        env = build_envelope(
            status='partial',
            summary='ambiguous',
            kind='read',
            capability='analytics',
            recovery={'recoverable': True, 'failure_kind': 'ambiguous'},
            state_delta={
                'open_threads': [
                    {'kind': 'clarify', 'key': 'scope', 'message': 'which app?'}
                ],
            },
        )
        as_dict = env.as_dict()
        self.assertIn('recovery', as_dict)
        self.assertIn('state_delta', as_dict)
        self.assertEqual(as_dict['recovery']['failure_kind'], 'ambiguous')
        rebuilt = ToolEnvelopeModel.model_validate(as_dict)
        assert rebuilt.recovery is not None
        self.assertEqual(rebuilt.recovery.failure_kind, 'ambiguous')

    def test_legacy_envelope_without_new_fields_is_byte_identical(self):
        legacy = build_envelope(
            status='ok',
            summary='done',
            kind='read',
            capability='analytics',
            reason_code=None,
            payload={'q': 'x'},
        )
        as_dict = legacy.as_dict()
        self.assertNotIn('recovery', as_dict)
        self.assertNotIn('state_delta', as_dict)
        # All pre-Phase-1 keys still present, in the same order.
        self.assertEqual(
            list(as_dict.keys()),
            ['status', 'summary', 'outcome', 'payload'],
        )

    def test_error_envelope_remains_legacy_shape(self):
        err = error_envelope(
            capability='analytics',
            reason_code='SQL_TIMEOUT',
            summary='timeout',
        )
        as_dict = err.as_dict()
        self.assertNotIn('recovery', as_dict)
        self.assertNotIn('state_delta', as_dict)
        self.assertEqual(as_dict['status'], 'error')

    def test_invalid_failure_kind_is_rejected(self):
        with self.assertRaises(Exception):
            build_envelope(
                status='partial',
                summary='bad',
                kind='read',
                capability='analytics',
                recovery={'recoverable': True, 'failure_kind': 'mystery'},
            )


# ---------------------------------------------------------------------------
# Scratchpad merge / apply
# ---------------------------------------------------------------------------


class ApplyStateDeltaTests(unittest.TestCase):
    def test_apply_state_delta_merges_typed_blocks(self):
        pad = default_scratchpad()
        apply_state_delta(
            pad,
            {
                'confirmed_constraints': [
                    {
                        'key': 'run_id',
                        'value': 'r1',
                        'provenance': 'user_explicit',
                        'source_tool': 'resolve_entity',
                    },
                ],
                'grounded_refs': [
                    {
                        'kind': 'run',
                        'key': 'run_id',
                        'value': 'r1',
                        'provenance': 'resolver_derived',
                    },
                ],
                'open_threads': [
                    {'kind': 'clarify', 'key': 'scope', 'message': 'which?'},
                ],
                'last_result': {
                    'kind': 'chart',
                    'artifact_type': 'bar',
                    'row_count': 11,
                },
                'failure_record': {
                    'failure_kind': 'empty',
                    'recoverable': True,
                    'reason_code': 'CG_EMPTY',
                    'summary': 'empty slice',
                },
            },
        )
        self.assertEqual(len(pad['confirmed_constraints']), 1)
        self.assertEqual(pad['confirmed_constraints'][0]['key'], 'run_id')
        self.assertEqual(len(pad['grounded_refs']), 1)
        self.assertEqual(pad['open_threads'][0]['message'], 'which?')
        self.assertEqual(pad['last_result']['kind'], 'chart')
        self.assertEqual(pad['last_failure']['failure_kind'], 'empty')

    def test_apply_state_delta_is_additive_not_destructive(self):
        pad = default_scratchpad()
        pad['findings'].append('prior finding')
        pad['active_filters'] = {
            'status': {'value': 'VIOLATED', 'provenance': 'user_explicit'},
        }
        apply_state_delta(
            pad,
            {
                'confirmed_constraints': [
                    {'key': 'run_id', 'value': 'r1', 'provenance': 'user_explicit'},
                ],
            },
        )
        # Unrelated state untouched.
        self.assertEqual(pad['findings'], ['prior finding'])
        self.assertEqual(pad['active_filters']['status']['value'], 'VIOLATED')
        # New state present.
        self.assertEqual(pad['confirmed_constraints'][0]['key'], 'run_id')

    def test_apply_state_delta_dedup_replaces_same_key(self):
        pad = default_scratchpad()
        apply_state_delta(
            pad,
            {
                'confirmed_constraints': [
                    {
                        'key': 'run_id',
                        'value': 'old',
                        'provenance': 'user_explicit',
                        'source_tool': 'resolve_entity',
                    },
                ],
            },
        )
        apply_state_delta(
            pad,
            {
                'confirmed_constraints': [
                    {
                        'key': 'run_id',
                        'value': 'new',
                        'provenance': 'user_explicit',
                        'source_tool': 'resolve_entity',
                    },
                ],
            },
        )
        self.assertEqual(len(pad['confirmed_constraints']), 1)
        self.assertEqual(pad['confirmed_constraints'][0]['value'], 'new')

    def test_apply_state_delta_ignores_unknown_top_level_keys(self):
        pad = default_scratchpad()
        apply_state_delta(
            pad,
            {
                'confirmed_constraints': [
                    {'key': 'a', 'value': 1, 'provenance': 'user_explicit'},
                ],
                # Arbitrary extra keys must not leak into the scratchpad.
                'secret_internal_blob': {'a': 'b'},
                'arbitrary_list': [1, 2, 3],
            },
        )
        self.assertNotIn('secret_internal_blob', pad)
        self.assertNotIn('arbitrary_list', pad)

    def test_apply_state_delta_no_op_when_state_delta_missing(self):
        pad = default_scratchpad()
        snapshot = json.dumps(pad, sort_keys=True)
        apply_state_delta(pad, None)
        apply_state_delta(pad, {})
        self.assertEqual(json.dumps(pad, sort_keys=True), snapshot)

    def test_apply_tool_recovery_records_last_failure_when_kind_non_none(self):
        pad = default_scratchpad()
        apply_tool_recovery(
            pad,
            {'recoverable': True, 'failure_kind': 'empty'},
            reason_code='CG_EMPTY',
            summary='empty slice',
        )
        self.assertEqual(pad['last_failure']['failure_kind'], 'empty')
        self.assertTrue(pad['last_failure']['recoverable'])
        self.assertEqual(pad['last_failure']['reason_code'], 'CG_EMPTY')

    def test_apply_tool_recovery_is_noop_for_failure_kind_none(self):
        pad = default_scratchpad()
        apply_tool_recovery(
            pad, {'recoverable': True, 'failure_kind': 'none'}, reason_code=None
        )
        self.assertIsNone(pad['last_failure'])

    def test_confirmed_constraint_and_grounded_ref_compat_views(self):
        pad = default_scratchpad()
        apply_state_delta(
            pad,
            {
                'confirmed_constraints': [
                    {'key': 'run_id', 'value': 'r1', 'provenance': 'user_explicit'},
                    {'key': 'status', 'value': 'VIOLATED', 'provenance': 'user_explicit'},
                ],
                'grounded_refs': [
                    {'kind': 'run', 'key': 'run_id', 'value': 'r1', 'provenance': 'resolver_derived'},
                    {'kind': 'run', 'key': 'run_id', 'value': 'r2', 'provenance': 'resolver_derived', 'source_tool': 'other'},
                ],
            },
        )
        self.assertEqual(
            confirmed_constraint_values(pad),
            {'run_id': 'r1', 'status': 'VIOLATED'},
        )
        self.assertEqual(grounded_ref_values(pad), {'run': ['r1', 'r2']})

    def test_resolve_open_thread_removes_entry(self):
        pad = default_scratchpad()
        apply_state_delta(
            pad,
            {
                'open_threads': [
                    {'kind': 'clarify', 'key': 'scope', 'message': 'which?'},
                    {'kind': 'clarify', 'key': 'time', 'message': 'when?'},
                ],
            },
        )
        resolve_open_thread(pad, kind='clarify', key='scope')
        self.assertEqual(len(pad['open_threads']), 1)
        self.assertEqual(pad['open_threads'][0]['key'], 'time')


# ---------------------------------------------------------------------------
# Recovery-context rendering (prompt assembly)
# ---------------------------------------------------------------------------


class BuildRecoveryContextTests(unittest.TestCase):
    def test_returns_none_when_empty(self):
        pad = default_scratchpad()
        self.assertIsNone(build_recovery_context(pad))
        self.assertIsNone(render_recovery_context_block(pad))

    def test_surfaces_prior_failure_open_threads_last_result(self):
        pad = default_scratchpad()
        apply_state_delta(
            pad,
            {
                'open_threads': [
                    {'kind': 'clarify', 'key': 'scope', 'message': 'which app?'},
                ],
                'last_result': {
                    'kind': 'empty',
                    'artifact_type': 'chart',
                    'row_count': 0,
                    'reason_code': 'CG_EMPTY',
                },
                'failure_record': {
                    'failure_kind': 'empty',
                    'recoverable': True,
                    'reason_code': 'CG_EMPTY',
                    'summary': 'empty slice',
                },
            },
        )
        ctx = build_recovery_context(pad)
        self.assertIsNotNone(ctx)
        assert ctx is not None
        self.assertEqual(ctx['prior_failure']['failure_kind'], 'empty')
        self.assertTrue(ctx['prior_failure']['recoverable'])
        self.assertEqual(ctx['open_threads'][0]['message'], 'which app?')
        self.assertEqual(ctx['last_result']['row_count'], 0)

        block = render_recovery_context_block(pad)
        assert block is not None
        self.assertIn('RECOVERY CONTEXT:', block)
        self.assertIn('Prior failure: empty (recoverable)', block)
        self.assertIn('reason_code=CG_EMPTY', block)
        self.assertIn('Open clarification threads:', block)
        self.assertIn('which app?', block)
        self.assertIn('Last result:', block)

    def test_scratchpad_prompt_block_includes_recovery_context(self):
        """The Layer-4 scratchpad renderer surfaces the recovery block."""
        from app.services.chat_engine.prompts import scratchpad as scratchpad_layer

        session: dict = {'scratchpad': default_scratchpad()}
        apply_state_delta(
            session['scratchpad'],
            {
                'open_threads': [
                    {'kind': 'clarify', 'key': 'scope', 'message': 'which app exactly?'},
                ],
                'failure_record': {
                    'failure_kind': 'ambiguous',
                    'recoverable': True,
                },
            },
        )
        rendered = scratchpad_layer.render(session)
        self.assertIn('RECOVERY CONTEXT:', rendered)
        self.assertIn('which app exactly?', rendered)
        self.assertIn('ambiguous', rendered)


# ---------------------------------------------------------------------------
# Default scratchpad shape — backward-compat keys still present
# ---------------------------------------------------------------------------


class DefaultScratchpadBackwardCompatTests(unittest.TestCase):
    def test_default_scratchpad_retains_legacy_keys_and_adds_new_ones(self):
        pad = default_scratchpad()
        for key in (
            'findings',
            'errors',
            'discovery',
            'lookups',
            'resolved_entities',
            'active_filters',
            'discovered_schema',
            'last_analysis',
            'analysis_history',
            'last_evidence',
            'last_data_check',
            'outcomes',
        ):
            self.assertIn(key, pad)
        for key in (
            'confirmed_constraints',
            'grounded_refs',
            'open_threads',
            'last_result',
            'last_failure',
        ):
            self.assertIn(key, pad)

    def test_build_previous_turn_context_still_works_without_state_delta(self):
        """Regression guard: analytics compat helpers unaffected by Phase 1."""
        previous_turn = scratchpad_state.build_previous_turn_context(
            {
                'last_analysis': {
                    'question': 'x',
                    'row_count': 1,
                    'columns': ['c'],
                    'chart_summary': {'kind': 'chart', 'mark': 'bar'},
                },
                'active_filters': {'status': 'VIOLATED'},
                'outcomes': [
                    {
                        'tool': 'data_query',
                        'artifact_type': 'chart',
                        'reason_code': None,
                        'counts': {'rows': 1},
                    }
                ],
            }
        )
        assert previous_turn is not None
        self.assertEqual(previous_turn['user_goal'], 'x')
        self.assertEqual(previous_turn['result_kind'], 'chart')


# ---------------------------------------------------------------------------
# Base prompt carries the recovery / clarification policy
# ---------------------------------------------------------------------------


class BasePromptRecoveryPolicyTests(unittest.TestCase):
    def test_base_prompt_contains_recovery_policy_section(self):
        from app.services.chat_engine.prompts import base

        prompt = base.render()
        self.assertIn('RECOVERY AND CLARIFICATION POLICY', prompt)
        # Failure-kind vocabulary locked into the prompt.
        for kind in (
            'ambiguous',
            'empty',
            'invalid_reference',
        ):
            self.assertIn(kind, prompt)
        # "one crisp clarifying question" is the required wording per plan.
        self.assertIn('one crisp clarifying question', prompt)


# ---------------------------------------------------------------------------
# Tool-description generator exposes generic recovery semantics once
# ---------------------------------------------------------------------------


class ToolDescriptionRecoverySemanticsTests(unittest.TestCase):
    def test_render_recovery_semantics_is_generic_and_short(self):
        from app.services.chat_engine.tool_description_generator import (
            render_recovery_semantics,
        )

        text = render_recovery_semantics()
        # Generic vocabulary is present.
        self.assertIn('recovery', text)
        self.assertIn('state_delta', text)
        for kind in (
            'ambiguous',
            'empty',
            'invalid_reference',
            'unsupported',
            'permission',
            'tool_error',
        ):
            self.assertIn(kind, text)
        # Keep it generic — no pack-specific next-action catalogs.
        self.assertNotIn('CG_', text)
        self.assertNotIn('SQL_', text)
        # Reasonable length — one paragraph, not endless prose.
        self.assertLess(len(text), 1200)

    def test_recovery_semantics_token_is_substituted_in_tool_descriptions(self):
        from unittest.mock import MagicMock

        from app.services.chat_engine.tool_description_generator import (
            fill_tool_description,
        )

        pack = MagicMock()
        pack.output_schema = MagicMock(return_value=None)
        pack.tool_reason_codes = MagicMock(return_value=())
        pack.tool_limitations = MagicMock(return_value=())

        spec = {
            'name': 'demo',
            'description': 'Demo. {{recovery_semantics}}',
            'inputSchema': {'properties': {}},
        }

        # ``get_manifest`` is imported at module import time; patch the
        # module attribute rather than the original symbol.
        from unittest.mock import patch

        with patch(
            'app.services.chat_engine.tool_description_generator.get_manifest',
            return_value=MagicMock(catalog_tables={}, data_surfaces=[]),
        ):
            filled = fill_tool_description(spec, app_id='kaira-bot', pack=pack)

        self.assertNotIn('{{recovery_semantics}}', filled['description'])
        self.assertIn('Recovery semantics', filled['description'])


# ---------------------------------------------------------------------------
# End-to-end: _update_scratchpad applies state_delta + recovery
# ---------------------------------------------------------------------------


class UpdateScratchpadWithStateDeltaTests(unittest.TestCase):
    def test_update_scratchpad_applies_state_delta_and_recovery(self):
        from app.services.report_builder.chat_handler import _update_scratchpad

        session: dict = {'scratchpad': default_scratchpad()}
        envelope = {
            'status': 'partial',
            'summary': 'empty slice',
            'outcome': {
                'kind': 'read',
                'capability': 'analytics',
                'reason_code': 'CG_EMPTY',
                'warnings': [],
                'counts': {'rows': 0, 'records': 0, 'affected': 0},
            },
            'payload': {'question': 'q', 'status': 'ok', 'row_count': 0},
            'recovery': {'recoverable': True, 'failure_kind': 'empty'},
            'state_delta': {
                'open_threads': [
                    {'kind': 'clarify', 'key': 'scope', 'message': 'which app?'}
                ],
                'failure_record': {
                    'failure_kind': 'empty',
                    'recoverable': True,
                    'reason_code': 'CG_EMPTY',
                    'summary': 'empty slice',
                },
            },
        }

        _update_scratchpad(session, 'data_query', json.dumps(envelope), app_id='')
        pad = session['scratchpad']

        self.assertEqual(
            pad['open_threads'][0]['message'], 'which app?'
        )
        self.assertEqual(pad['last_failure']['failure_kind'], 'empty')

    def test_update_scratchpad_is_unchanged_when_envelope_lacks_new_fields(self):
        from app.services.report_builder.chat_handler import _update_scratchpad

        session: dict = {'scratchpad': default_scratchpad()}
        envelope = {
            'status': 'ok',
            'summary': 'ok',
            'outcome': {
                'kind': 'read',
                'capability': 'analytics',
                'reason_code': None,
                'warnings': [],
                'counts': {'rows': 1, 'records': 0, 'affected': 0},
            },
            'payload': {'question': 'q', 'status': 'ok', 'row_count': 1},
        }

        _update_scratchpad(session, 'data_query', json.dumps(envelope), app_id='')
        pad = session['scratchpad']

        # New Phase-1 blocks remain empty/defaulted — envelope didn't emit them.
        self.assertEqual(pad['confirmed_constraints'], [])
        self.assertEqual(pad['grounded_refs'], [])
        self.assertEqual(pad['open_threads'], [])
        self.assertIsNone(pad['last_failure'])
        # Legacy outcomes log still records the call.
        self.assertEqual(pad['outcomes'][-1]['tool'], 'data_query')


if __name__ == '__main__':
    unittest.main()
