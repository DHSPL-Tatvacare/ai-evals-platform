"""Deterministic pack auto-layout — pure `layout_new_nodes`.

The pack assigns positions for NEW nodes only: topological columns
left->right, branches/siblings stacked in rows, anchored to the right of the
connect-anchor and below the lowest existing node so existing nodes are never
moved or overlapped.
"""
from __future__ import annotations

import unittest

from app.services.orchestration_authoring.layout import layout_new_nodes


class TwoChainedNewNodesTest(unittest.TestCase):
    """(a) two new chained nodes get distinct, non-overlapping positions in
    left->right columns."""

    def test_chained_new_nodes_advance_columns(self) -> None:
        nodes = [
            {'id': 'a', 'type': 'source.cohort'},
            {'id': 'b', 'type': 'messaging.send_whatsapp_template'},
        ]
        edges = [{'id': 'e1', 'source': 'a', 'target': 'b'}]
        result = layout_new_nodes(
            nodes=nodes,
            edges=edges,
            new_node_ids={'a', 'b'},
            existing_positions={},
        )

        self.assertIn('a', result)
        self.assertIn('b', result)
        # distinct positions
        self.assertNotEqual(
            (result['a']['x'], result['a']['y']),
            (result['b']['x'], result['b']['y']),
        )
        # b is downstream of a -> a strictly to the left of b
        self.assertLess(result['a']['x'], result['b']['x'])


class ExistingNodeUntouchedTest(unittest.TestCase):
    """(b) given an existing node at a known position, new nodes are placed
    without overlapping it and the existing position is returned unchanged."""

    def test_existing_position_preserved_and_no_overlap(self) -> None:
        existing = {'old': {'x': 100.0, 'y': 200.0}}
        nodes = [
            {'id': 'old', 'type': 'source.cohort'},
            {'id': 'new1', 'type': 'messaging.send_whatsapp_template'},
        ]
        edges = [{'id': 'e1', 'source': 'old', 'target': 'new1'}]
        result = layout_new_nodes(
            nodes=nodes,
            edges=edges,
            new_node_ids={'new1'},
            existing_positions=existing,
        )

        # existing node returned unchanged
        self.assertEqual(result['old'], {'x': 100.0, 'y': 200.0})
        # new node placed and not coincident with the existing node
        self.assertIn('new1', result)
        self.assertNotEqual(
            (result['new1']['x'], result['new1']['y']),
            (existing['old']['x'], existing['old']['y']),
        )
        # new subgraph anchored below the lowest existing node
        self.assertGreater(result['new1']['y'], existing['old']['y'])


class BranchStackingTest(unittest.TestCase):
    """(c) a branch (two children of one node) stacks the children in
    separate rows."""

    def test_two_children_stack_in_rows(self) -> None:
        nodes = [
            {'id': 'p', 'type': 'logic.conditional'},
            {'id': 'c1', 'type': 'messaging.send_whatsapp_template'},
            {'id': 'c2', 'type': 'voice.place_call'},
        ]
        edges = [
            {'id': 'e1', 'source': 'p', 'target': 'c1'},
            {'id': 'e2', 'source': 'p', 'target': 'c2'},
        ]
        result = layout_new_nodes(
            nodes=nodes,
            edges=edges,
            new_node_ids={'p', 'c1', 'c2'},
            existing_positions={},
        )

        # children share a column to the right of the parent
        self.assertEqual(result['c1']['x'], result['c2']['x'])
        self.assertGreater(result['c1']['x'], result['p']['x'])
        # stacked in separate rows
        self.assertNotEqual(result['c1']['y'], result['c2']['y'])


if __name__ == '__main__':
    unittest.main()
