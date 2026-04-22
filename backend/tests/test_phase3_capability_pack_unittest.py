"""Phase 3 acceptance-gate tests (plan §Phase-3 → *Acceptance gates*).

Gates pinned here map 1:1 to the plan:

1. ``len(CAPABILITY_PACK_REGISTRY) >= 2`` at boot; validator raises on
   unknown pack id in any app config.
2. Every tool description rendered via
   ``resolve_tools(..., app_id='kaira-bot')`` contains a non-empty
   ``{{output_schema}}`` substitution, AND every resolved spec carries
   a machine-readable top-level ``outputSchema`` (plan §6.3 Protocol).
3. Malformed arguments fail at the Agents SDK boundary — the SDK's
   strict schema validation sits between the model and
   ``_parse_tool_args``, which is narrowed to the ``"{}"`` no-args path.
4. Memoized ``resolve_tools`` returns the same object identity for the
   same ``(pack_ids, app_id)`` across 100 consecutive calls.
5. Tool descriptions flow through each pack's ``describe_tools(app_id)``
   method — Harness Core doesn't look up description strings directly.
"""

from __future__ import annotations

import json
import unittest


class RegistryPopulationTests(unittest.TestCase):
    def test_registry_has_at_least_analytics_and_report_builder(self):
        from app.services.chat_engine.capability_pack import (
            CAPABILITY_PACK_REGISTRY,
            ensure_packs_registered,
        )

        ensure_packs_registered()
        self.assertGreaterEqual(len(CAPABILITY_PACK_REGISTRY), 2)
        self.assertIn('analytics', CAPABILITY_PACK_REGISTRY)
        self.assertIn('report_builder', CAPABILITY_PACK_REGISTRY)

    def test_unknown_pack_id_raises(self):
        from app.services.chat_engine.capability_pack import resolve_pack_ids_for_app

        with self.assertRaises(RuntimeError) as ctx:
            resolve_pack_ids_for_app(['analytics', 'does-not-exist'], app_id='kaira-bot')
        self.assertIn('does-not-exist', str(ctx.exception))


class OutputSchemaTests(unittest.TestCase):
    """Plan §6.3 Protocol: each spec MUST carry ``inputSchema`` AND
    ``outputSchema``. The generator-rendered description MUST also contain
    the filled ``{{output_schema}}`` substitution."""

    def test_every_resolved_spec_carries_outputSchema(self):
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        tools = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')
        missing = [t['name'] for t in tools if 'outputSchema' not in t]
        self.assertEqual(
            missing, [],
            f'tools missing top-level outputSchema: {missing}',
        )
        # outputSchema is a JSON Schema object — type + properties present.
        for tool in tools:
            os = tool['outputSchema']
            self.assertIsInstance(os, dict)
            self.assertEqual(os.get('type'), 'object')
            self.assertIn('properties', os)

    def test_every_tool_description_contains_output_schema_block(self):
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        tools = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')
        self.assertGreater(len(tools), 0)
        for tool in tools:
            desc = tool.get('description', '')
            self.assertIn(
                'Output fields:', desc,
                f"tool {tool.get('name')!r} description missing {{{{output_schema}}}} block: {desc[:200]!r}",
            )
            # Raw templated tokens MUST be fully substituted — none may leak.
            self.assertNotIn('{{output_schema}}', desc)
            self.assertNotIn('{{reason_codes}}', desc)
            self.assertNotIn('{{limitations}}', desc)


class PackDescribeToolsRoutingTests(unittest.TestCase):
    """Plan §6.3 rule 3: every pack owns its own ``describe_tools()``.
    The main resolution path MUST route through it — not reach around
    into ``fill_tool_description`` directly for the top-level string."""

    def test_resolved_description_equals_pack_describe_tools_output(self):
        from app.services.chat_engine.capability_pack import CAPABILITY_PACK_REGISTRY
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        tools = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')

        for pack_id in ('analytics', 'report_builder'):
            pack = CAPABILITY_PACK_REGISTRY[pack_id]
            described = dict(pack.describe_tools('kaira-bot'))
            for name, pack_description in described.items():
                resolved = next((t for t in tools if t['name'] == name), None)
                self.assertIsNotNone(resolved, f'tool {name!r} missing from resolved list')
                self.assertEqual(
                    resolved['description'], pack_description,
                    f'tool {name!r} description diverges from pack.describe_tools output',
                )


class MemoizationIdentityTests(unittest.TestCase):
    def test_resolve_tools_returns_same_object_across_100_calls(self):
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        first = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')
        for _ in range(100):
            again = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')
            self.assertIs(again, first)

    def test_different_pack_ids_produce_different_results(self):
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        analytics_only = resolve_tools(['analytics'], app_id='kaira-bot')
        both = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')
        self.assertIsNot(analytics_only, both)
        self.assertLess(len(analytics_only), len(both))


class StrictSchemaBoundaryTests(unittest.TestCase):
    """Plan §Phase-3 step 4: tools run in strict schema mode; malformed
    args fail at the SDK boundary before the handler runs. The parser is
    narrowed to the ``""`` / ``"{}"`` / whitespace no-args contract."""

    def test_function_tools_use_strict_mode(self):
        from app.services.chat_engine.openai_agents_adapter import build_sherlock_tools

        tools = build_sherlock_tools([
            {
                'name': 'demo',
                'description': 'x',
                'inputSchema': {
                    'type': 'object',
                    'properties': {'q': {'type': 'string'}},
                    'required': ['q'],
                },
            },
        ])
        self.assertTrue(tools[0].strict_json_schema)

    def test_every_pack_spec_is_strict_compatible(self):
        """Strict-schema transformation must accept every pack-contributed
        inputSchema without raising ``UserError`` (no lingering
        ``additionalProperties: true`` or similar incompatibilities)."""
        from app.services.chat_engine.openai_agents_adapter import build_sherlock_tools
        from app.services.report_builder.tool_definitions import (
            _clear_resolve_tools_cache_for_tests,
            resolve_tools,
        )

        _clear_resolve_tools_cache_for_tests()
        tools = resolve_tools(['analytics', 'report_builder'], app_id='kaira-bot')
        # Must not raise.
        built = build_sherlock_tools(tools)
        self.assertEqual(len(built), len(tools))
        for ft in built:
            self.assertTrue(ft.strict_json_schema)

    def test_parse_tool_args_narrowed_to_empty_contract(self):
        """Phase 3: only empty / whitespace / ``"{}"`` recovers to ``{}``;
        anything else is a contract violation. The handler's ``try/except``
        projects raises into a ``MALFORMED_ARGS`` envelope so the outer
        agent still observes a typed reason code."""
        from app.services.chat_engine.openai_agents_adapter import _parse_tool_args

        self.assertEqual(_parse_tool_args('{}'), {})
        self.assertEqual(_parse_tool_args(''), {})
        self.assertEqual(_parse_tool_args('   '), {})
        self.assertEqual(_parse_tool_args('{"q":"ok"}'), {'q': 'ok'})

        with self.assertRaises(json.JSONDecodeError):
            _parse_tool_args('{not-json')
        with self.assertRaises(ValueError):
            _parse_tool_args('null')
        with self.assertRaises(ValueError):
            _parse_tool_args('[1,2]')


class BootTimePackValidatorTests(unittest.IsolatedAsyncioTestCase):
    """Plan §Phase-3 acceptance gate: ``resolve_pack_ids_for_app`` raises
    on unknown pack ids. ``validate_all_app_pack_ids`` runs the same
    check against every active app at boot so drift fails loudly."""

    async def test_boot_validator_raises_on_unknown_pack_id_in_app_config(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.chat_engine.capability_pack import validate_all_app_pack_ids

        # Two rows: one valid (caps=['analytics']) and one invalid.
        class _FakeResult:
            def all(self):
                return [
                    ('kaira-bot', {
                        'displayName': 'Kaira', 'icon': 'k', 'description': '',
                        'chat': {'capabilities': ['analytics']},
                    }),
                    ('broken-app', {
                        'displayName': 'Broken', 'icon': 'b', 'description': '',
                        'chat': {'capabilities': ['does-not-exist']},
                    }),
                ]

        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult())

        with self.assertRaises(RuntimeError) as ctx:
            await validate_all_app_pack_ids(db)
        self.assertIn('does-not-exist', str(ctx.exception))

    async def test_boot_validator_accepts_all_known_pack_ids(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.chat_engine.capability_pack import validate_all_app_pack_ids

        class _FakeResult:
            def all(self):
                return [
                    ('kaira-bot', {
                        'displayName': 'Kaira', 'icon': 'k', 'description': '',
                        'chat': {'capabilities': ['analytics', 'report_builder']},
                    }),
                ]

        db = MagicMock()
        db.execute = AsyncMock(return_value=_FakeResult())

        await validate_all_app_pack_ids(db)  # must not raise


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
