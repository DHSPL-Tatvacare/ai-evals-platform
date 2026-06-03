"""The ONE writer of ``analytics.fact_workflow_engagement`` + the ``agg_workflow_run`` matview.

Reads the orchestration TXN spine and collapses each recipient's many action rows on a capability
into one engagement row: the most-advanced ``outcome_bucket`` (resolved via the adapter registry,
never null), dispatch/attempt/cost/talk-time rollups, and the resolved connection. Bucket rank and
connection resolution — formerly live in ``read_service`` — live here now. Idempotent per run
(delete-then-insert), then the per-run rollup matview is rebuilt. No request handler writes either.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics_workflow_facts import FactWorkflowEngagement
from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowVersion,
)
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.adapters import registered_adapter_instances
from app.services.orchestration.analytics.outcomes import EngagementBucket

logger = logging.getLogger(__name__)

# Most-advanced wins (matches read_service._BUCKET_RANK): positive is strongest, in_flight weakest;
# an unresolved/null bucket ranks 0 and never wins.
_BUCKET_RANK = {
    EngagementBucket.positive.value: 5,
    EngagementBucket.reached.value: 4,
    EngagementBucket.no_response.value: 3,
    EngagementBucket.failed.value: 2,
    EngagementBucket.in_flight.value: 1,
}
_DISPATCH_NODE_TYPES = ("voice.place_call", "messaging.send_whatsapp_template", "core.webhook_out")

# Dispatch-marker action_types (voice_queued/wa_dispatched/webhook_out_posted) carry no
# ACTION_OUTCOME_MAP entry, so capability falls back to the row's channel (a generic data value).
# channel == capability for voice/webhook; whatsapp folds into the messaging capability.
_CHANNEL_TO_CAPABILITY = {"voice": "voice", "whatsapp": "messaging", "wa": "messaging", "webhook": "webhook"}


def _capability_index() -> tuple[dict[str, str], dict[str, str]]:
    """Registry-derived maps: action_type→capability, action_type→bucket value."""
    type_to_cap: dict[str, str] = {}
    type_to_bucket: dict[str, str] = {}
    for adapter in registered_adapter_instances():
        capability = getattr(adapter, "capability", None)
        outcome_map = getattr(adapter, "ACTION_OUTCOME_MAP", None)
        if not capability or not outcome_map:
            continue
        for action_type, bucket in outcome_map.items():
            type_to_cap[action_type] = capability
            type_to_bucket[action_type] = bucket.value
    return type_to_cap, type_to_bucket


def _extract_connection_ids(definition: dict[str, Any]) -> dict[str, str]:
    """node_id → connection_id for dispatch nodes in a version definition (mirrors read_service)."""
    out: dict[str, str] = {}
    for node in (definition or {}).get("nodes") or []:
        if node.get("type") not in _DISPATCH_NODE_TYPES:
            continue
        conn = (node.get("config") or {}).get("connection_id")
        if conn:
            out[str(node.get("id"))] = str(conn)
    return out


def _num(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


class WorkflowEngagementPopulator:
    """Rebuilds the workflow-engagement fact + matview from the TXN spine. Idempotent per run."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._type_to_cap, self._type_to_bucket = _capability_index()

    async def populate(self, *, tenant_id: uuid.UUID | None = None, app_id: str | None = None,
                        run_ids: list[uuid.UUID] | None = None) -> dict:
        runs = await self._load_runs(tenant_id=tenant_id, app_id=app_id, run_ids=run_ids)
        totals = {"runs": 0, "engagement_rows": 0}
        for run in runs:
            rows = await self._populate_run(run)
            totals["runs"] += 1
            totals["engagement_rows"] += rows
        await self._refresh_rollup()
        await self.db.commit()
        logger.info("workflow analytics populated: %d runs, %d engagement rows", totals["runs"], totals["engagement_rows"])
        return totals

    async def _load_runs(self, *, tenant_id, app_id, run_ids) -> list[WorkflowRun]:
        stmt = select(WorkflowRun)
        if run_ids:
            stmt = stmt.where(WorkflowRun.id.in_(run_ids))
        if tenant_id:
            stmt = stmt.where(WorkflowRun.tenant_id == tenant_id)
        if app_id:
            stmt = stmt.where(WorkflowRun.app_id == app_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def _populate_run(self, run: WorkflowRun) -> int:
        await self.db.execute(
            delete(FactWorkflowEngagement).where(FactWorkflowEngagement.run_id == run.id)
        )
        workflow_name = await self.db.scalar(select(Workflow.name).where(Workflow.id == run.workflow_id))
        node_to_conn = await self._node_connection_map(run)
        conn_meta = await self._connection_meta(node_to_conn.values())
        lead_ids = await self._lead_id_set(run)

        # actions + their node_id (for connection resolution), ordered for stable last-event picks
        rows = (await self.db.execute(
            select(WorkflowRunRecipientAction, WorkflowRunNodeStep.node_id)
            .join(WorkflowRunNodeStep, WorkflowRunRecipientAction.node_step_id == WorkflowRunNodeStep.id)
            .where(WorkflowRunRecipientAction.run_id == run.id)
            .order_by(WorkflowRunRecipientAction.created_at, WorkflowRunRecipientAction.id)
        )).all()

        groups: dict[tuple[str, str], list[tuple[WorkflowRunRecipientAction, str]]] = {}
        for action, node_id in rows:
            capability = self._type_to_cap.get(action.action_type) or _CHANNEL_TO_CAPABILITY.get(action.channel)
            if capability is None:
                continue  # non-dispatch action (logic/sink/source) — not an engagement
            groups.setdefault((action.recipient_id, capability), []).append((action, node_id))

        count = 0
        for (recipient_id, capability), members in groups.items():
            self.db.add(self._build_row(
                run=run, workflow_name=workflow_name, recipient_id=recipient_id, capability=capability,
                members=members, node_to_conn=node_to_conn, conn_meta=conn_meta, lead_ids=lead_ids,
            ))
            count += 1
        await self.db.flush()
        return count

    def _build_row(self, *, run, workflow_name, recipient_id, capability, members,
                   node_to_conn, conn_meta, lead_ids) -> FactWorkflowEngagement:
        actions = [a for a, _ in members]
        # per-row resolved bucket + rank
        row_buckets = [
            (a, a.outcome_bucket or self._type_to_bucket.get(a.action_type)) for a in actions
        ]
        best_rank, best_bucket = 0, None
        for _a, bucket in row_buckets:
            rank = _BUCKET_RANK.get(bucket, 0)
            if rank > best_rank:
                best_rank, best_bucket = rank, bucket
        # best_rank==0 → no real bucket observed (pure-dispatch); keep the in_flight sentinel for leaf
        # integrity but mark unresolved so the matview/breakdown leave it uncounted (read_service parity).
        bucket_resolved = best_rank > 0
        outcome_bucket = best_bucket if best_bucket else EngagementBucket.in_flight.value

        dispatch_rows = [a for a in actions if a.parent_action_id is None]
        cost = Decimal(0)
        cost_rows = 0
        duration_sec = Decimal(0)
        talk_count = 0
        for a, bucket in row_buckets:
            resp = a.response if isinstance(a.response, dict) else {}
            tc = _num(resp.get("total_cost"))
            if tc is not None:
                cost += tc
                cost_rows += 1
            if bucket == EngagementBucket.positive.value:
                ds = _num(resp.get("duration_sec"))
                if ds is not None:
                    duration_sec += ds
                    talk_count += 1

        # connection from a dispatch row's node (fall back to any member's node)
        conn_id = None
        for a, node_id in members:
            if a.parent_action_id is None:
                conn_id = node_to_conn.get(node_id)
                if conn_id:
                    break
        if conn_id is None:
            for _a, node_id in members:
                conn_id = node_to_conn.get(node_id)
                if conn_id:
                    break
        provider, conn_name = conn_meta.get(conn_id or "", (None, None))

        contact = next((a.payload.get("contact") for a in actions
                        if isinstance(a.payload, dict) and a.payload.get("contact")), None)
        provider_status = next((a.provider_status for a in reversed(actions) if a.provider_status), None)
        first_dispatched_at = min((a.created_at for a in dispatch_rows), default=None)
        last_event_at = max((a.completed_at or a.created_at for a in actions), default=None)

        return FactWorkflowEngagement(
            tenant_id=run.tenant_id, app_id=run.app_id,
            workflow_id=run.workflow_id, workflow_name=workflow_name,
            run_id=run.id, workflow_version_id=run.workflow_version_id,
            recipient_id=recipient_id,
            lead_id=recipient_id if recipient_id in lead_ids else None,
            contact_e164=contact,
            capability=capability, channel=actions[0].channel,
            connection_id=_uuid_or_none(conn_id),
            connection_label=conn_name or ("unmapped" if conn_id is None else conn_id),
            provider=provider,
            outcome_bucket=outcome_bucket,
            bucket_resolved=bucket_resolved,
            dispatched=bool(dispatch_rows),
            dispatch_attempts=len(dispatch_rows),
            attempts=len(actions),
            cost=cost, cost_rows=cost_rows,
            duration_sec=duration_sec, talk_count=talk_count,
            provider_status=provider_status,
            triggered_by=run.triggered_by, run_status=run.status,
            cohort_size_at_entry=run.cohort_size_at_entry,
            run_started_at=run.started_at, first_dispatched_at=first_dispatched_at,
            last_event_at=last_event_at, run_completed_at=run.completed_at,
            created_at=datetime.now(tz=run.started_at.tzinfo) if run.started_at else None,
        )

    async def _node_connection_map(self, run: WorkflowRun) -> dict[str, str]:
        definition = await self.db.scalar(
            select(WorkflowVersion.definition).where(WorkflowVersion.id == run.workflow_version_id)
        )
        return _extract_connection_ids(definition or {})

    async def _connection_meta(self, conn_ids) -> dict[str, tuple[str | None, str | None]]:
        uuids = [u for u in {_uuid_or_none(c) for c in conn_ids} if u]
        if not uuids:
            return {}
        rows = (await self.db.execute(
            select(ProviderConnection.id, ProviderConnection.provider, ProviderConnection.name)
            .where(ProviderConnection.id.in_(uuids))
        )).all()
        return {str(cid): (provider, name) for cid, provider, name in rows}

    async def _lead_id_set(self, run: WorkflowRun) -> set[str]:
        """recipient_ids that actually bridge to analytics.dim_lead (per-cohort contract, not invariant)."""
        rows = (await self.db.execute(
            text(
                "SELECT s.recipient_id FROM orchestration.workflow_run_recipient_states s "
                "JOIN analytics.dim_lead dl ON dl.lead_id::text = s.recipient_id AND dl.app_id = s.app_id "
                "WHERE s.run_id = :run_id"
            ),
            {"run_id": str(run.id)},
        )).all()
        return {r[0] for r in rows}

    async def _refresh_rollup(self) -> None:
        await self.db.execute(text("REFRESH MATERIALIZED VIEW analytics.agg_workflow_run"))


async def populate_workflow_engagement(
    db: AsyncSession, *, tenant_id: uuid.UUID | None = None, app_id: str | None = None,
    run_ids: list[uuid.UUID] | None = None,
) -> dict:
    """Entry point: rebuild the engagement fact + matview for the scoped runs (all runs if unscoped)."""
    return await WorkflowEngagementPopulator(db).populate(tenant_id=tenant_id, app_id=app_id, run_ids=run_ids)


def build_populate_job(run: WorkflowRun):
    """A queued ``populate-workflow-analytics`` BackgroundJob for one run — enqueued by the
    post-run-completion and post-reconcile hooks so engagement analytics refresh asynchronously."""
    from app.constants import SYSTEM_USER_ID
    from app.models.job import BackgroundJob

    job_user_id = run.triggered_by_user_id or SYSTEM_USER_ID
    return BackgroundJob(
        id=uuid.uuid4(), tenant_id=run.tenant_id, app_id=run.app_id, user_id=job_user_id,
        job_type="populate-workflow-analytics", queue_class="bulk", priority=5,
        params={"run_id": str(run.id), "tenant_id": str(run.tenant_id), "user_id": str(job_user_id)},
        status="queued",
    )
