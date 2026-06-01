"""TASK #3 — pure resolve_connection_ladder across all four rungs.

No DB. Drives the cat-A connection_picker resolution ladder:
  1. hint fuzzy-match (one clear best -> resolved; ties -> pick; none -> fall through)
  2. default_id in candidates -> resolved
  3. exactly one candidate -> resolved
  4. else -> pick (or none when empty)
"""
from __future__ import annotations

import unittest

from app.services.orchestration_authoring.connection_resolver import (
    ConnRef,
    resolve_connection_ladder,
)


def _ref(id_: str, name: str, provider: str) -> ConnRef:
    return ConnRef(id=id_, name=name, provider=provider)


class HintRungTests(unittest.TestCase):
    def test_hint_fuzzy_resolves_single_best_match_on_provider(self) -> None:
        candidates = [
            _ref('c1', 'Marketing line', 'wati'),
            _ref('c2', 'Voice line', 'bolna'),
        ]
        res = resolve_connection_ladder(
            candidates=candidates, default_id=None, hint='bolna',
        )
        self.assertEqual(res.status, 'resolved')
        assert res.connection is not None
        self.assertEqual(res.connection.id, 'c2')

    def test_hint_fuzzy_resolves_on_name(self) -> None:
        candidates = [
            _ref('c1', 'Marketing line', 'wati'),
            _ref('c2', 'Support line', 'wati'),
        ]
        res = resolve_connection_ladder(
            candidates=candidates, default_id=None, hint='marketing',
        )
        self.assertEqual(res.status, 'resolved')
        assert res.connection is not None
        self.assertEqual(res.connection.id, 'c1')

    def test_ambiguous_hint_returns_pick_with_tied_candidates(self) -> None:
        candidates = [
            _ref('c1', 'Support one', 'wati'),
            _ref('c2', 'Support two', 'wati'),
        ]
        res = resolve_connection_ladder(
            candidates=candidates, default_id=None, hint='support',
        )
        self.assertEqual(res.status, 'pick')
        ids = {c.id for c in (res.candidates or [])}
        self.assertEqual(ids, {'c1', 'c2'})

    def test_hint_no_match_falls_through_to_lower_rung(self) -> None:
        # hint matches nothing, but there is a single candidate -> rung 3 resolves
        candidates = [_ref('c1', 'Marketing line', 'wati')]
        res = resolve_connection_ladder(
            candidates=candidates, default_id=None, hint='zzzzzzz',
        )
        self.assertEqual(res.status, 'resolved')
        assert res.connection is not None
        self.assertEqual(res.connection.id, 'c1')


class DefaultRungTests(unittest.TestCase):
    def test_default_in_candidates_resolves(self) -> None:
        candidates = [
            _ref('c1', 'Marketing line', 'wati'),
            _ref('c2', 'Support line', 'wati'),
        ]
        res = resolve_connection_ladder(
            candidates=candidates, default_id='c2', hint=None,
        )
        self.assertEqual(res.status, 'resolved')
        assert res.connection is not None
        self.assertEqual(res.connection.id, 'c2')

    def test_default_not_in_candidates_falls_through_to_pick(self) -> None:
        candidates = [
            _ref('c1', 'Marketing line', 'wati'),
            _ref('c2', 'Support line', 'wati'),
        ]
        res = resolve_connection_ladder(
            candidates=candidates, default_id='gone', hint=None,
        )
        self.assertEqual(res.status, 'pick')
        self.assertEqual(len(res.candidates or []), 2)


class SingleAndEmptyRungTests(unittest.TestCase):
    def test_single_candidate_resolves(self) -> None:
        candidates = [_ref('c1', 'Marketing line', 'wati')]
        res = resolve_connection_ladder(
            candidates=candidates, default_id=None, hint=None,
        )
        self.assertEqual(res.status, 'resolved')
        assert res.connection is not None
        self.assertEqual(res.connection.id, 'c1')

    def test_multiple_no_hint_no_default_returns_pick(self) -> None:
        candidates = [
            _ref('c1', 'Marketing line', 'wati'),
            _ref('c2', 'Support line', 'wati'),
        ]
        res = resolve_connection_ladder(
            candidates=candidates, default_id=None, hint=None,
        )
        self.assertEqual(res.status, 'pick')
        self.assertEqual(len(res.candidates or []), 2)

    def test_empty_candidates_returns_none(self) -> None:
        res = resolve_connection_ladder(
            candidates=[], default_id=None, hint=None,
        )
        self.assertEqual(res.status, 'none')
        self.assertIsNone(res.connection)


if __name__ == '__main__':
    unittest.main()
