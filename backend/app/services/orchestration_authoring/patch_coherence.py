"""Patch-time coherence: payload-bound dispatch fields must be carried by an
upstream inline source.cohort anywhere in the ancestor chain. Pure, DB-free —
complements ``validate_definition`` (edges/handles/branch-ids/acyclicity)."""
from __future__ import annotations

from typing import Any

from app.services.orchestration.upstream_variables import collect_ancestors


def _bound_payload_fields(node: dict[str, Any]) -> list[str]:
    """Payload field names a dispatch node binds (source_kind=='payload')."""
    fields: list[str] = []
    for row in (node.get("config") or {}).get("variable_mappings") or []:
        if not isinstance(row, dict):
            continue
        if row.get("source_kind", "payload") != "payload":
            continue  # static literals carry their own value; nothing upstream to check
        field = row.get("payload_field")
        if field:
            fields.append(field)
    return fields


def check_bound_fields_carried(candidate: dict[str, Any]) -> list[str]:
    """Return one violation per payload-bound field that no ancestor inline
    ``source.cohort`` carries. Walks the FULL ancestor chain (shared
    ``collect_ancestors``) so intermediate logic/wait/extract nodes between
    source and dispatch do not hide the carrier.

    Only inline ``source.cohort`` is checked. Saved-mode cohorts carry their
    fields on ``CohortDefinitionVersion`` in the DB (not on the node config),
    and ``source.dataset`` columns also need a DB lookup — both are out of
    scope for this DB-free check and are skipped rather than mis-flagged.
    """
    nodes_by_id: dict[str, dict[str, Any]] = {
        n.get("id"): n for n in candidate.get("nodes") or [] if n.get("id")
    }
    edge_pairs: list[tuple[str, str]] = [
        (e.get("source"), e.get("target"))
        for e in candidate.get("edges") or []
        if e.get("source") and e.get("target")
    ]

    violations: list[str] = []
    for node in candidate.get("nodes") or []:
        bound = _bound_payload_fields(node)
        if not bound:
            continue
        carried: set[str] = set()
        unverifiable_upstream = False
        for ancestor_id in collect_ancestors(node.get("id"), edge_pairs):
            upstream = nodes_by_id.get(ancestor_id)
            if upstream is None:
                continue
            up_type = upstream.get("type")
            # Saved-mode cohorts and datasets carry their fields in the DB, not
            # on the node config — invisible to this DB-free check. Their
            # presence makes the carrier set unprovable, so suppress flagging.
            if up_type == "source.dataset":
                unverifiable_upstream = True
                continue
            if up_type != "source.cohort":
                continue
            if (upstream.get("config") or {}).get("mode") != "inline":
                unverifiable_upstream = True
                continue
            carried.update((upstream.get("config") or {}).get("payload_fields") or [])
        if unverifiable_upstream:
            continue
        for field in bound:
            if field not in carried:
                violations.append(
                    f"node {node.get('id')!r} binds payload field {field!r} but no "
                    f"upstream inline source.cohort carries it"
                )
    return violations


__all__ = ["check_bound_fields_carried"]
