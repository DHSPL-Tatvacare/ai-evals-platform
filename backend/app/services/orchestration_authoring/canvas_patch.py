"""CanvasPatch artifact contract — `orchestration.canvas_patch.v1`.

The terminal `apply_patch` tool emits exactly one CanvasPatch per turn.
The frontend applier (Phase 2) translates each op into a
`workflowBuilderStore` mutation.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CANVAS_PATCH_CONTRACT_ID = 'orchestration.canvas_patch.v1'


CanvasPatchOpKind = Literal[
    'add_node',
    'update_node_config',
    'connect',
    'remove_node',
]


class CanvasPatchOp(BaseModel):
    """One mutation in a CanvasPatch.

    `op` discriminates the shape of `payload`:
      - add_node: payload = {node_type: str, position?: {x,y}, config: dict}
      - update_node_config: payload = {config_patch: dict}  (shallow merge)
      - connect: payload = {source_node_id, output_id, target_node_id, edge_id}
      - remove_node: payload = {}  (cascades edges)

    `node_id` is the node the op operates on. For `connect`, it is the
    source node id (the edge id is in the payload).
    """

    model_config = ConfigDict(extra='forbid')

    op: CanvasPatchOpKind
    node_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CanvasPatch(BaseModel):
    """The artifact emitted by `apply_patch` and consumed by the frontend.

    `base_data_hash` is the load-bearing optimistic-concurrency anchor:
    the frontend rejects the patch on mismatch and prompts the user to
    rebase rather than clobbering.
    """

    model_config = ConfigDict(extra='forbid')

    workflow_id: str
    version_id: str | None = None
    base_data_hash: str
    ops: list[CanvasPatchOp] = Field(default_factory=list)
    rationale: str = ''


__all__ = [
    'CANVAS_PATCH_CONTRACT_ID',
    'CanvasPatchOp',
    'CanvasPatchOpKind',
    'CanvasPatch',
]
