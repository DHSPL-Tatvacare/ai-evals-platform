"""Single writer of the ingress choke table ``orchestration.workflow_run_recipients``."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import (
    CohortDefinitionVersion,
    WorkflowRun,
    WorkflowRunRecipient,
)
from app.utils.phone import normalise_phone_e164


@dataclass(frozen=True)
class RegisterReceipt:
    registered_count: int
    unresolved_phone_count: int
    predicate_hash: Optional[str]


def _hash_predicate_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_predicate(version: CohortDefinitionVersion) -> str:
    return _hash_predicate_payload(
        {
            "version_id": str(version.id),
            "source_ref": version.source_ref,
            "filters": version.filters or [],
            "payload_fields": version.payload_fields or [],
            "lookback_hours": version.lookback_hours,
            "lookback_column": version.lookback_column,
            "consent_gate_channel": version.consent_gate_channel,
        }
    )


async def register_run_recipients(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    ingress_kind: str,
    resolved_rows: Iterable[tuple[str, str | None]],
    cohort_version: CohortDefinitionVersion | None = None,
    inline_predicate: dict | None = None,
    provenance: dict | None = None,
) -> RegisterReceipt:
    """Register the run's recipient membership into the single choke table.

    Cohort, dataset, and event ingress all call this after materializing their
    recipient set. Membership is unconditional: ``resolved_rows`` yields
    ``(recipient_id, raw_phone)`` and every recipient_id becomes a member.
    ``phone_e164`` is best-effort provenance — an unresolvable phone leaves it
    NULL (counted in ``unresolved_phone_count``) but the row is still written
    so ``assert_recipient_in_manifest`` passes for all ingress. The write is
    idempotent against the ``(run_id, recipient_id)`` unique constraint.

    ``predicate_hash`` and ``source_cohort_version_id`` are populated for
    cohort ingress (saved-mode hashes the version; inline-mode hashes the
    resolved query shape); they stay NULL for dataset / event ingress.
    """
    if cohort_version is not None:
        predicate_hash: Optional[str] = _hash_predicate(cohort_version)
        source_cohort_version_id = cohort_version.id
    elif inline_predicate:
        predicate_hash = _hash_predicate_payload(inline_predicate)
        source_cohort_version_id = None
    else:
        predicate_hash = None
        source_cohort_version_id = None

    registered = 0
    unresolved = 0
    rows_to_insert: list[dict] = []
    for recipient_id, raw_phone in resolved_rows:
        e164 = normalise_phone_e164(raw_phone)
        if e164 is None:
            unresolved += 1
        rows_to_insert.append(
            {
                "run_id": run.id,
                "tenant_id": run.tenant_id,
                "app_id": run.app_id,
                "recipient_id": recipient_id,
                "phone_e164": e164,
                "source_cohort_version_id": source_cohort_version_id,
                "predicate_hash": predicate_hash,
                "ingress_kind": ingress_kind,
                "provenance": provenance,
            }
        )
        registered += 1
    if rows_to_insert:
        stmt = pg_insert(WorkflowRunRecipient).values(rows_to_insert)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_workflow_run_recipients_run_recipient"
        )
        await db.execute(stmt)
        await db.flush()
    return RegisterReceipt(
        registered_count=registered,
        unresolved_phone_count=unresolved,
        predicate_hash=predicate_hash,
    )
