"""BuilderSnapshot — per-turn canvas context handed to the authoring_specialist.

The route handler builds this from `pageContext` after passing R1 (route
gate). The supervisor and authoring_specialist read it from
`SherlockTurnContext.builder_context`. The canvas snapshot is rendered
into the specialist's system prompt at agent build time (no
describe_workflow tool — see SDK conformance review §E).
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


WorkflowType = Literal['crm', 'clinical']
ViewMode = Literal['view', 'edit']


class BuilderSnapshot(BaseModel):
    """Trusted-after-validation per-turn canvas context.

    The route handler validates `workflow_id` ownership against the
    requesting tenant (404 on mismatch — never leak). `definition` is
    treated as untrusted input shape-wise (re-validated as a dict here)
    but trusted for content because the user is editing it on the
    frontend right now; `data_hash` is the integrity anchor used by the
    frontend applier.
    """

    model_config = ConfigDict(extra='forbid')

    workflow_id: uuid.UUID
    version_id: uuid.UUID | None = None
    workflow_type: WorkflowType
    app_id: str
    definition: dict[str, Any] = Field(default_factory=dict)
    data_hash: str
    selected_node_id: str | None = None
    view_mode: ViewMode = 'edit'


__all__ = ['BuilderSnapshot', 'WorkflowType', 'ViewMode']
