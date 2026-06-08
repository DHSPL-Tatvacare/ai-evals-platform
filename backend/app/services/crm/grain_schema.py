"""The closed list of bind targets per grain, introspected from the ORM (single source of truth).

The mapping editor offers exactly these targets so a binding can never invent a column or
slot. Standard columns are named; the typed slot pool is generic capacity for domain fields.
Derived columns (``phone_number_norm``) and plumbing are never offered.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric

from app.models.crm import CrmActivity, CrmActivityExt, CrmLead, CrmLeadExt

_PLUMBING = frozenset({"id", "tenant_id", "app_id", "crm_lead_id", "crm_activity_id"})
_DERIVED = frozenset({"phone_number_norm"})  # set by the unpacker, never mapped

_GRAINS = {
    "lead": {
        "core": CrmLead, "ext": CrmLeadExt,
        "natural_key_target": "lead_id",
        "lead_link_target": "lead_id",
        "lead_link_required": False,
        "expected_targets": ["lead_id", "phone_number", "lead_stage"],
    },
    "activity": {
        "core": CrmActivity, "ext": CrmActivityExt,
        "natural_key_target": "source_activity_id",
        "lead_link_target": "lead_id",
        "lead_link_required": True,
        "expected_targets": ["source_activity_id", "lead_id"],
    },
}

_SLOT_TYPE_BY_PREFIX = {"txt": "text", "int": "int", "num": "num", "dt": "dt", "bool": "bool", "json": "json"}


def _data_type(column) -> str:
    t = column.type
    if isinstance(t, (Integer, BigInteger)):
        return "int"
    if isinstance(t, Numeric):
        return "num"
    if isinstance(t, DateTime):
        return "datetime"
    if isinstance(t, Boolean):
        return "bool"
    return "text"


def _humanise(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _standard_columns(core) -> list[dict]:
    cols = []
    for name, col in core.__table__.columns.items():
        if name in _PLUMBING or name in _DERIVED:
            continue
        cols.append({"target": name, "label": _humanise(name), "data_type": _data_type(col)})
    return cols


def _slots(ext) -> dict[str, list[str]]:
    pool: dict[str, list[str]] = {"text": [], "int": [], "num": [], "dt": [], "bool": [], "json": []}
    for name in ext.__table__.columns.keys():
        if name in _PLUMBING:
            continue
        prefix = name.split("_")[0]
        kind = _SLOT_TYPE_BY_PREFIX.get(prefix)
        if kind:
            pool[kind].append(name)
    for kind in pool:
        pool[kind].sort()
    return pool


def grain_schema(record_type: str) -> dict:
    """Return the bind-target catalogue for a grain (standard columns + typed slot pool)."""
    meta = _GRAINS.get(record_type)
    if meta is None:
        raise ValueError(f"unknown grain {record_type!r}; expected one of {sorted(_GRAINS)}")
    return {
        "record_type": record_type,
        "natural_key_target": meta["natural_key_target"],
        "lead_link_target": meta["lead_link_target"],
        "lead_link_required": meta["lead_link_required"],
        "expected_targets": list(meta["expected_targets"]),
        "standard_columns": _standard_columns(meta["core"]),
        "slots": _slots(meta["ext"]),
    }


def all_grain_schemas() -> list[dict]:
    return [grain_schema(rt) for rt in _GRAINS]


__all__ = ["all_grain_schemas", "grain_schema"]
