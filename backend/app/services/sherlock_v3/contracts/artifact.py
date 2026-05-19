"""Artifact — UI-bound discriminated payload union."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


ArtifactKind = Literal['chart', 'kpi', 'summary', 'table', 'citation_set', 'empty']


class Artifact(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: ArtifactKind
    payload: dict[str, Any]
