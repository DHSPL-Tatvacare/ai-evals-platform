"""Deterministic pack auto-layout for newly authored nodes.

The agent never hand-places nodes. ``layout_new_nodes`` assigns a position to
each NEW node by topological depth (columns left->right), stacking sibling
branches in rows. The new subgraph is anchored to the right of its connect
anchor and below the lowest existing node so it never overlaps or rearranges
nodes the user already placed. Existing nodes keep their positions.
"""
from __future__ import annotations

from typing import Any

COLUMN_SPACING = 320.0
ROW_SPACING = 160.0


def layout_new_nodes(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    new_node_ids: set[str],
    existing_positions: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Return ``{node_id: {x, y}}`` for every NEW node; echo existing ones unchanged.

    New nodes are placed by topological depth within the new subgraph. Depth 0
    is anchored to the right of its upstream existing anchor (or origin when
    none); each depth occupies a column, and same-depth nodes stack in rows.
    The whole new block is shifted below the lowest existing node so it never
    collides with the user's layout.
    """
    out: dict[str, dict[str, float]] = {
        nid: dict(pos) for nid, pos in existing_positions.items()
    }

    new_ids = {nid for nid in new_node_ids if nid in {n.get('id') for n in nodes}}
    if not new_ids:
        return out

    incoming: dict[str, list[str]] = {nid: [] for nid in new_ids}
    for edge in edges:
        src = edge.get('source')
        tgt = edge.get('target')
        if tgt in new_ids:
            incoming[tgt].append(src)

    # Topological depth within the new subgraph; edges from existing nodes count
    # as depth -1 anchors so a new node wired off an existing node starts at 0.
    depth: dict[str, int] = {}

    def _depth(nid: str, seen: frozenset[str]) -> int:
        if nid in depth:
            return depth[nid]
        if nid in seen:
            return 0
        parents = [p for p in incoming.get(nid, []) if p in new_ids]
        if not parents:
            d = 0
        else:
            d = 1 + max(_depth(p, seen | {nid}) for p in parents)
        depth[nid] = d
        return d

    for nid in new_ids:
        _depth(nid, frozenset())

    # Anchor x: right of the right-most existing anchor feeding the new subgraph.
    anchor_x = 0.0
    for edge in edges:
        if edge.get('target') in new_ids and edge.get('source') in existing_positions:
            anchor_x = max(anchor_x, existing_positions[edge['source']].get('x', 0.0))

    # Anchor y: below the lowest existing node so the new block never overlaps.
    base_y = 0.0
    if existing_positions:
        base_y = max(p.get('y', 0.0) for p in existing_positions.values()) + ROW_SPACING

    by_depth: dict[int, list[str]] = {}
    for nid in sorted(new_ids):
        by_depth.setdefault(depth[nid], []).append(nid)

    for d, ids in by_depth.items():
        col_x = anchor_x + (d + 1) * COLUMN_SPACING
        for row, nid in enumerate(ids):
            out[nid] = {'x': col_x, 'y': base_y + row * ROW_SPACING}

    return out


__all__ = ['layout_new_nodes', 'COLUMN_SPACING', 'ROW_SPACING']
