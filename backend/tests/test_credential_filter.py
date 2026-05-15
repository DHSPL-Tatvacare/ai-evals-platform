"""Phase 3 Step 3 — recursive credential filter coverage.

Asserts the canonical `assert_no_credentials` walker raises on the
first forbidden field at any nesting depth, is case-insensitive on
field names, and passes clean payloads through unchanged.

The blocklist (`FORBIDDEN_FIELD_NAMES`) is the canonical source per
Decision §R5; tests here lock the surface so the egress filter cannot
silently regress.
"""
from __future__ import annotations

import unittest

from app.services.orchestration_authoring.credential_field_filter import (
    FORBIDDEN_FIELD_NAMES,
    CredentialLeakError,
    assert_no_credentials,
)


class BlocklistShapeTests(unittest.TestCase):
    def test_canonical_blocklist_matches_decision_r5(self) -> None:
        self.assertEqual(
            FORBIDDEN_FIELD_NAMES,
            frozenset({
                'api_key',
                'secret',
                'access_token',
                'config_encrypted',
                'password',
                'bearer',
                'webhook_token',
                'bolna_api_key',
                'wati_api_key',
            }),
        )

    def test_blocklist_is_immutable(self) -> None:
        self.assertIsInstance(FORBIDDEN_FIELD_NAMES, frozenset)


class CleanPayloadTests(unittest.TestCase):
    def test_empty_dict_passes(self) -> None:
        assert_no_credentials({})

    def test_empty_list_passes(self) -> None:
        assert_no_credentials([])

    def test_primitives_pass(self) -> None:
        for value in (None, 1, 1.5, 'hello', True, False, b'\x00'):
            assert_no_credentials(value)

    def test_clean_nested_payload_passes(self) -> None:
        assert_no_credentials({
            'items': [
                {'id': 'a', 'name': 'wati-prod', 'provider': 'wati'},
                {'id': 'b', 'meta': {'tags': ['prod', 'live']}},
            ],
            'count': 2,
        })


class LeakDetectionTests(unittest.TestCase):
    def test_top_level_api_key(self) -> None:
        with self.assertRaises(CredentialLeakError) as cm:
            assert_no_credentials({'api_key': 'sk-abc'})
        self.assertEqual(cm.exception.field_name, 'api_key')

    def test_nested_5_levels_deep(self) -> None:
        payload = {
            'l1': {
                'l2': {
                    'l3': {
                        'l4': {
                            'l5': {'api_key': 'sk-abc'},
                        },
                    },
                },
            },
        }
        with self.assertRaises(CredentialLeakError) as cm:
            assert_no_credentials(payload)
        self.assertEqual(cm.exception.field_name, 'api_key')
        # Path captures the full route through the dict.
        self.assertEqual(
            cm.exception.path,
            ['l1', 'l2', 'l3', 'l4', 'l5', 'api_key'],
        )

    def test_inside_list_of_dicts(self) -> None:
        payload = {
            'items': [
                {'id': 'a'},
                {'id': 'b', 'secret': 'leak'},
            ],
        }
        with self.assertRaises(CredentialLeakError) as cm:
            assert_no_credentials(payload)
        self.assertEqual(cm.exception.field_name, 'secret')
        # Index of the offending list entry is captured in the path.
        self.assertIn(1, cm.exception.path)

    def test_each_blocklist_member_is_caught(self) -> None:
        for name in FORBIDDEN_FIELD_NAMES:
            with self.assertRaises(CredentialLeakError, msg=f'{name} not caught'):
                assert_no_credentials({name: 'leak'})

    def test_case_insensitive_matching(self) -> None:
        # Mixed-case Api_Key trips the filter just like api_key.
        for variant in ('API_KEY', 'Api_Key', 'apI_KeY'):
            with self.assertRaises(CredentialLeakError) as cm:
                assert_no_credentials({variant: 'leak'})
            self.assertEqual(cm.exception.field_name, variant)

    def test_first_hit_short_circuits(self) -> None:
        # Two leaks: walker raises on the first one it visits and stops.
        payload = {
            'first': {'api_key': 'a'},
            'second': {'secret': 'b'},
        }
        with self.assertRaises(CredentialLeakError) as cm:
            assert_no_credentials(payload)
        # The exception always names a real forbidden key — order is
        # dict-iteration-dependent, but it MUST be one of the two.
        self.assertIn(cm.exception.field_name, {'api_key', 'secret'})

    def test_non_string_keys_are_skipped(self) -> None:
        # Pure-numeric keys are not credential-shaped; only string keys
        # match. (Defensive — JSON-shaped payloads always have str keys.)
        assert_no_credentials({1: 'ok', 2: {'inner': 'safe'}})

    def test_clean_payload_is_not_mutated(self) -> None:
        payload = {'items': [{'id': 'x'}]}
        before = repr(payload)
        assert_no_credentials(payload)
        self.assertEqual(repr(payload), before)


if __name__ == '__main__':
    unittest.main()
