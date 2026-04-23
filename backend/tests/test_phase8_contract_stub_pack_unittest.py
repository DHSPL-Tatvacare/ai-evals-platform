"""Phase 8 — ``contract_stub`` proof-pack acceptance tests.

Pinned to the plan:
- §Phase-8 acceptance: at least one non-analytics pack can plug into the
  harness without forking orchestration; adding a pack does not require
  re-centering core runtime state.
- §6.3 Protocol: every pack satisfies ``CapabilityPack`` end-to-end.
- §6.2 envelope: tool returns have exact top-level shape.

These tests drive the real resolve_tools + adapter exit paths — they
are the philosophy demo, not pack-local unit tests.
"""
from __future__ import annotations

import asyncio
import unittest
from typing import Any


class StubPackProtocolTests(unittest.TestCase):
    """Binding §6.3 Protocol conformance + registry discovery."""

    def test_stub_pack_conforms_to_capability_pack_protocol(self):
        from app.services.chat_engine.capability_pack import (
            CAPABILITY_PACK_REGISTRY,
            CapabilityPack,
            ensure_packs_registered,
        )

        ensure_packs_registered()
        self.assertIn('contract_stub', CAPABILITY_PACK_REGISTRY)
        pack = CAPABILITY_PACK_REGISTRY['contract_stub']

        self.assertIsInstance(pack, CapabilityPack)
        self.assertEqual(pack.pack_id, 'contract_stub')

        # Protocol surface present + non-empty
        self.assertTrue(pack.tool_specs())
        self.assertTrue(pack.tool_handlers())
        self.assertTrue(pack.artifact_contracts)
        self.assertTrue(pack.artifact_extras_contracts)

        for method in ('tool_specs', 'tool_handlers', 'validate_arguments',
                       'describe_tools', 'build_outcome'):
            self.assertTrue(callable(getattr(pack, method)),
                            f'missing callable: {method}')


class StubPackReasonCodeTests(unittest.TestCase):
    """Pack owns its own reason codes; disjoint from every other pack."""

    def test_stub_pack_reason_codes_are_registered_and_disjoint(self):
        from app.services.chat_engine.capability_pack import ensure_packs_registered
        from app.services.chat_engine import reason_codes as harness_reason_codes
        from app.services.contract_stub.reason_codes import (
            CONTRACT_STUB_EMPTY_TEXT,
            CONTRACT_STUB_PACK_REASON_CODES,
            CONTRACT_STUB_TEXT_TOO_LONG,
            CONTRACT_STUB_UNKNOWN_VARIANT,
        )

        ensure_packs_registered()

        for code in (CONTRACT_STUB_EMPTY_TEXT,
                     CONTRACT_STUB_TEXT_TOO_LONG,
                     CONTRACT_STUB_UNKNOWN_VARIANT):
            self.assertIn(code, CONTRACT_STUB_PACK_REASON_CODES)

        registered = harness_reason_codes.PACK_REASON_CODES['contract_stub']
        self.assertTrue(CONTRACT_STUB_PACK_REASON_CODES.issubset(registered))

        # Disjoint from every other pack's non-shared codes.
        shared = harness_reason_codes.HARNESS_SHARED_REASON_CODES
        stub_local = CONTRACT_STUB_PACK_REASON_CODES - shared
        for other_pack, other_codes in harness_reason_codes.PACK_REASON_CODES.items():
            if other_pack == 'contract_stub':
                continue
            other_local = other_codes - shared
            overlap = stub_local & other_local
            self.assertEqual(
                overlap, set(),
                f'contract_stub reason codes collide with {other_pack}: {overlap!r}',
            )


class StubPackResolveToolsTests(unittest.TestCase):
    """``resolve_tools`` must discover stub tools with no hand-edits in
    ``tool_definitions.py``."""

    def test_resolve_tools_includes_stub_pack_without_tool_definitions_edits(self):
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        tools = resolve_tools(
            ['analytics', 'report_builder', 'contract_stub'],
            app_id='voice-rx',
        )
        names = {t['name'] for t in tools}
        self.assertIn('stub_capabilities', names)
        self.assertIn('stub_make_note', names)

        by_name = {t['name']: t for t in tools}

        # Description came from the pack's describe_tools(): {{output_schema}}
        # substitution produced a non-empty ``Output fields:`` block.
        for name in ('stub_capabilities', 'stub_make_note'):
            desc = by_name[name].get('description', '')
            self.assertIn('Output fields:', desc,
                          f'{name} description missing {{{{output_schema}}}} block')
            self.assertNotIn('{{output_schema}}', desc)
            self.assertNotIn('{{reason_codes}}', desc)
            self.assertNotIn('{{limitations}}', desc)
            self.assertIn('outputSchema', by_name[name],
                          f'{name} spec missing outputSchema')
            self.assertIsInstance(by_name[name]['outputSchema'], dict)

        # And the description strictly matches what the pack's describe_tools
        # produced (plan §6.3 rule 3: pack is the only source of truth).
        from app.services.chat_engine.capability_pack import CAPABILITY_PACK_REGISTRY
        pack = CAPABILITY_PACK_REGISTRY['contract_stub']
        pack_descs = pack.describe_tools(app_id='voice-rx')
        for name in ('stub_capabilities', 'stub_make_note'):
            self.assertEqual(by_name[name]['description'], pack_descs[name])


class StubMakeNoteEnvelopeTests(unittest.TestCase):
    """``stub_make_note`` returns the canonical §6.2 envelope shape."""

    def test_stub_make_note_returns_canonical_tool_envelope(self):
        from app.services.contract_stub.tool_handlers import handle_stub_make_note

        env = asyncio.run(handle_stub_make_note(text='hello', variant='plain')).as_dict()

        # Top-level keys EXACTLY status / summary / outcome / payload.
        self.assertEqual(
            set(env.keys()), {'status', 'summary', 'outcome', 'payload'},
            f'unexpected top-level keys: {sorted(env.keys())}',
        )
        self.assertEqual(env['status'], 'ok')

        outcome = env['outcome']
        self.assertEqual(outcome['kind'], 'artifact')
        self.assertEqual(outcome['capability'], 'contract_stub')
        self.assertEqual(outcome['reason_code'], None)

        artifact = outcome['artifact']
        self.assertIsInstance(artifact, dict)
        self.assertEqual(artifact['type'], 'note_card')
        self.assertEqual(artifact['contract'], 'contract_stub.note.v1')
        self.assertIn('extras', artifact)
        self.assertEqual(artifact['extras']['rendered_variant'], 'plain')
        self.assertFalse(artifact['extras']['truncated'])

        self.assertIn('note', env['payload'])
        note = env['payload']['note']
        self.assertEqual(note['title'], 'Stub note')
        self.assertEqual(note['body'], 'hello')
        self.assertEqual(note['variant'], 'plain')
        self.assertEqual(note['source_text'], 'hello')


class StubCapabilitiesEnvelopeTests(unittest.TestCase):
    def test_stub_capabilities_returns_read_envelope_without_artifact(self):
        from app.services.contract_stub.tool_handlers import handle_stub_capabilities

        env = asyncio.run(handle_stub_capabilities()).as_dict()
        self.assertEqual(
            set(env.keys()), {'status', 'summary', 'outcome', 'payload'},
        )
        outcome = env['outcome']
        self.assertEqual(outcome['kind'], 'read')
        self.assertEqual(outcome['capability'], 'contract_stub')
        self.assertIsNone(outcome.get('artifact'))
        self.assertEqual(env['payload']['variants'], ['plain', 'warning', 'success'])
        self.assertEqual(env['payload']['maxTextLength'], 120)


class AdapterDispatchAppendsArtifactTests(unittest.TestCase):
    """Drives the real adapter exit path (``_finalize_tool_call``) to prove
    the artifact lane is generic — no stub-specific code in the harness."""

    def test_adapter_dispatch_appends_stub_artifact_to_sherlock_context(self):
        import json

        from app.services.chat_engine.openai_agents_adapter import (
            SherlockContext,
            _finalize_tool_call,
        )
        from app.services.contract_stub.tool_handlers import handle_stub_make_note

        # Produce the exact envelope a real tool call would return.
        result_str = json.dumps(
            asyncio.run(
                handle_stub_make_note(text='hello', variant='warning'),
            ).as_dict(),
            default=str,
        )

        emitted: list[dict[str, Any]] = []

        async def emit(event: dict[str, Any]) -> None:
            emitted.append(event)

        sc = SherlockContext(
            auth=None,
            app_id='voice-rx',
            provider='openai',
            working_session={},
            emit=emit,
        )

        asyncio.run(_finalize_tool_call(
            sc=sc,
            tool_name='stub_make_note',
            tool_call_id='tc_stub_1',
            result_str=result_str,
            execution_ms=1.2,
            emitted_start=False,
        ))

        # Exactly one artifact appended via the generic lane.
        self.assertEqual(len(sc.artifacts), 1)
        artifact = sc.artifacts[0]
        self.assertEqual(artifact.pack_id, 'contract_stub')
        self.assertEqual(artifact.contract_id, 'contract_stub.note.v1')

        payload = artifact.payload
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload['title'], 'Stub warning')
        self.assertEqual(payload['variant'], 'warning')
        self.assertEqual(payload['source_text'], 'hello')

        self.assertEqual(artifact.extras.get('rendered_variant'), 'warning')
        self.assertFalse(artifact.extras.get('truncated'))

        # The generic egress projects artifact metadata onto the tool_call_end
        # event — no pack-specific event shape.
        end_events = [e for e in emitted if e.get('event') == 'tool_call_end']
        self.assertEqual(len(end_events), 1)
        outcome = end_events[0]['data']['outcome']
        self.assertEqual(outcome['capability'], 'contract_stub')
        self.assertEqual(outcome['artifact']['contract'], 'contract_stub.note.v1')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
