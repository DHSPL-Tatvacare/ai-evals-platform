"""Closed-list validation for ``crm_field_map`` bindings.

The "never invent a target" guarantee: a binding's ``slot`` must be a real
standard column OR a real generic slot on the grain's tables, and ``record_type``
must be ``lead`` | ``activity`` (``stage_transition`` is DERIVED, never mapped).
The closed list is INTROSPECTED from the ORM so it can never drift from the schema.
"""
from __future__ import annotations

import re

from app.models.crm import (
    CrmActivity,
    CrmActivityExt,
    CrmLead,
    CrmLeadExt,
)
from app.services.crm.grain_schema import registered_record_types

ALLOWED_RECORD_TYPES = frozenset(registered_record_types("crm"))

# A semantic_key becomes a SQL alias in the resolved matview/view DDL, so it must be a safe,
# lowercase SQL identifier within Postgres' 63-byte limit — never free text that could break out.
_SEMANTIC_KEY_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")

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


def validate_semantic_key(semantic_key: str) -> None:
    """Raise ``ValueError`` unless ``semantic_key`` is a safe lowercase SQL identifier.

    The key is interpolated as the output alias in the resolved matview/view DDL; an unvalidated
    value would be a raw-SQL identifier-injection vector, so it is closed-listed by grammar here.
    """
    if not _SEMANTIC_KEY_RE.fullmatch(semantic_key or ""):
        raise ValueError(
            f"semantic_key {semantic_key!r} must be a lowercase identifier "
            "(letters, digits, underscore; starting with a letter or underscore; max 63 chars)"
        )


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


__all__ = ["ALLOWED_RECORD_TYPES", "allowed_targets", "validate_binding", "validate_semantic_key"]
