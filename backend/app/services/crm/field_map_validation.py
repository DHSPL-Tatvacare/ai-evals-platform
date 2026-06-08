"""Closed-list validation for ``crm_field_map`` bindings.

The "never invent a target" guarantee: a binding's ``slot`` must be a real
standard column OR a real generic slot on the grain's tables, and ``record_type``
must be ``lead`` | ``activity`` (``stage_transition`` is DERIVED, never mapped).
The closed list is INTROSPECTED from the ORM so it can never drift from the schema.
"""
from __future__ import annotations

from app.models.crm import (
    CrmActivity,
    CrmActivityExt,
    CrmLead,
    CrmLeadExt,
)

ALLOWED_RECORD_TYPES = frozenset({"lead", "activity"})

# Columns that are scope/identity plumbing, never a bind target.
_NON_TARGET_COLUMNS = frozenset({"id", "tenant_id", "app_id", "crm_lead_id", "crm_activity_id"})

_GRAIN_MODELS = {
    "lead": (CrmLead, CrmLeadExt),
    "activity": (CrmActivity, CrmActivityExt),
}


def allowed_targets(record_type: str) -> frozenset[str]:
    """Standard columns + generic slots a binding may write for this grain."""
    core, ext = _GRAIN_MODELS[record_type]
    names: set[str] = set()
    for model in (core, ext):
        for col in model.__table__.columns.keys():
            if col not in _NON_TARGET_COLUMNS:
                names.add(col)
    return frozenset(names)


def validate_binding(record_type: str, slot: str) -> None:
    """Raise ``ValueError`` if the binding targets anything outside the closed list."""
    if record_type not in ALLOWED_RECORD_TYPES:
        raise ValueError(
            f"record_type must be one of {sorted(ALLOWED_RECORD_TYPES)}; got {record_type!r}"
        )
    targets = allowed_targets(record_type)
    if slot not in targets:
        raise ValueError(
            f"slot/target {slot!r} is not a valid {record_type} column or slot"
        )


__all__ = ["ALLOWED_RECORD_TYPES", "allowed_targets", "validate_binding"]
