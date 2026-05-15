"""Strict-mode policy for orchestration node configs.

Every node `_Config(BaseModel)` resolves its `model_config` through this
helper. Strictness is **unconditional**: unknown keys are rejected at
validation time. There is no flag, no rollback hatch, no env-driven
behaviour. If a workflow carries a field that is not declared on the
matching `_Config`, that workflow is broken and must be repaired — silent
drops were the bug class that let the authoring agent fabricate fields
like `prospect_ids` and `condition` without anyone noticing.

TODO (Phase 16): codegen Pydantic from a single source of truth and drop
this helper — strictness becomes a property of the generated model.
"""
from __future__ import annotations

from pydantic import ConfigDict


def strict_node_config_dict() -> ConfigDict:
    """Always `ConfigDict(extra='forbid')`. Call from every node `_Config`."""
    return ConfigDict(extra="forbid")


__all__ = ["strict_node_config_dict"]
