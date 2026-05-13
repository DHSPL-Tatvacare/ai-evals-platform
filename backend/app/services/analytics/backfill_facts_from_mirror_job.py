"""Generic mirror -> fact backfill job (Phase 4).

Drives a keyset-paginated scan over an analytics mirror table, projects each
batch through the Phase 2 ``MirrorToFactMapper``, and upserts into the target
fact table. One job submission backfills one
``(app_id, source_table, target_fact, activity_type)`` tuple — call backfill,
signal backfill, and stage-transition backfill are separate submissions per
plan §5.2.

Idempotency: the upsert uses the same conflict key the steady-state writer
does (Phase 3), so re-running the job over an already-populated window is
safe — fact rows are re-projected from the current mirror state and
``sync_run_id`` rotates to the backfill id. ``log_fact_population_run.metadata``
distinguishes inserted vs. updated row counts so operators can see whether a
replay actually changed anything.

Window semantics: ``started_after`` / ``ended_before`` are inclusive lower
and exclusive upper bounds on the mirror's source timestamp column
(``call_started_at`` for call rows, falling back to ``created_on`` when the
mirror row's ``call_started_at`` is NULL — same precedence used by Sherlock's
"calls" data surface today). Iteration order is the same coalesced timestamp
plus ``activity_id`` as a tiebreaker, so the cursor is stable across batches.

Each batch commits in its own transaction. A failure inside batch N rolls
back N's writes but leaves batches 0..N-1 committed — operators can re-run
with a tighter ``started_after`` to resume without re-doing successful work.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.analytics_lead_facts import FactLeadActivity
from app.models.analytics_log import LogFactPopulationRun
from app.models.source_records import CrmCallRecord, LogCrmSourceSync
from app.services.analytics.mirror_to_fact_mapper import (
    MappingProjectionError,
    MirrorToFactMapping,
    MirrorToFactMapper,
)

_log = logging.getLogger(__name__)

# ── tunables ─────────────────────────────────────────────────────────────

# Plan §5.2 example payload uses batch_size 5000. Anything materially larger
# stresses the JSONB insert path; anything smaller hurts wall-clock time on
# the ~65k inside-sales backfill. The admin endpoint clamps to this range.
MIN_BATCH_SIZE = 100
MAX_BATCH_SIZE = 10_000
DEFAULT_BATCH_SIZE = 5_000

# Plan invariant: this backfill writes into fact_lead_activity ONLY.
# Signal-fact backfill (Phase 5) and stage-transition backfill (Phase 6)
# get their own handlers because the target tables, conflict keys, and
# source columns differ. Refusing other targets here is defense in depth —
# the admin endpoint also gates it pre-submission.
SUPPORTED_TARGET_FACT = "analytics.fact_lead_activity"


# Each mirror table needs (a) the SQLAlchemy class to scan and (b) the
# column the cursor orders by. Today only crm_call_record is mapped; the
# registry grows when the next CRM activity-mirror table joins Phase 4.
@dataclass(frozen=True)
class _MirrorScanSpec:
    model: type
    # The mirror column the window filter (``started_after``/``ended_before``)
    # applies to. For calls this is the same coalesced expression used by the
    # Sherlock data surface so backfill row counts line up with the SQL the
    # operator runs against ``analytics.crm_call_record``.
    timestamp_column: Any
    # Column the cursor advances by alongside the timestamp. Must be unique
    # within the (tenant, app) scope so keyset pagination is deterministic.
    tiebreaker_column: Any


def _scan_spec_for(source_table: str) -> _MirrorScanSpec:
    if source_table == "analytics.crm_call_record":
        return _MirrorScanSpec(
            model=CrmCallRecord,
            timestamp_column=func.coalesce(
                CrmCallRecord.call_started_at, CrmCallRecord.created_on
            ),
            tiebreaker_column=CrmCallRecord.activity_id,
        )
    raise ValueError(
        f"no scan spec registered for source_table={source_table!r}; "
        "Phase 4 supports analytics.crm_call_record only"
    )


# ── request shape (validated by the admin endpoint, mirrored here) ───────


@dataclass(frozen=True)
class BackfillRequest:
    app_id: str
    source_table: str
    activity_type: str
    started_after: datetime | None
    ended_before: datetime | None
    batch_size: int


def parse_request(params: dict[str, Any]) -> BackfillRequest:
    """Parse + sanity-check params off a ``background_jobs.params`` dict.

    The admin endpoint is the primary entry point and validates against a
    Pydantic schema; this parser is the second line of defense for jobs
    submitted via other paths (replay tooling, ops console). Validation is
    intentionally duplicated rather than skipped because a malformed
    ``background_jobs.params`` row should crash the job loudly, not silently
    no-op.
    """
    app_id = str(params.get("app_id") or "").strip()
    source_table = str(params.get("source_table") or "").strip()
    activity_type = str(params.get("activity_type") or "").strip()

    if not app_id or not source_table or not activity_type:
        raise ValueError(
            "backfill-facts-from-mirror requires app_id, source_table, "
            "and activity_type"
        )

    batch_size = int(params.get("batch_size") or DEFAULT_BATCH_SIZE)
    if not MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch_size {batch_size} out of bounds "
            f"[{MIN_BATCH_SIZE}, {MAX_BATCH_SIZE}]"
        )

    return BackfillRequest(
        app_id=app_id,
        source_table=source_table,
        activity_type=activity_type,
        started_after=_coerce_optional_datetime(params.get("started_after")),
        ended_before=_coerce_optional_datetime(params.get("ended_before")),
        batch_size=batch_size,
    )


def _coerce_optional_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        # Bare naive datetimes are assumed UTC — the API serializes with
        # offsets but JSON column round-trips may strip tz info.
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        # Accept ISO 8601 with or without trailing Z. ``fromisoformat`` in
        # 3.11+ handles the Z directly; older callers normalize here.
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"invalid datetime literal {value!r}; expected ISO 8601"
            ) from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ValueError(
        f"unsupported datetime type {type(value).__name__} for backfill window"
    )


# ── counters / breadcrumb shape ──────────────────────────────────────────


@dataclass
class _BackfillCounters:
    pages: int = 0
    rows_scanned: int = 0
    rows_upserted: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    rows_errored: int = 0
    last_error: str | None = None
    # First few projection errors, surfaced in the log row so operators don't
    # have to grep container console for tracebacks. Capped to keep the
    # metadata JSONB bounded.
    error_samples: list[dict[str, Any]] = field(default_factory=list)

    def to_metadata(
        self,
        *,
        request: BackfillRequest,
        cursor_high_watermark: tuple[datetime | None, str | None],
        sync_run_id: uuid.UUID,
    ) -> dict[str, Any]:
        ts, tiebreak = cursor_high_watermark
        return {
            "app_id": request.app_id,
            "source_table": request.source_table,
            "activity_type": request.activity_type,
            "batch_size": request.batch_size,
            "started_after": request.started_after.isoformat() if request.started_after else None,
            "ended_before": request.ended_before.isoformat() if request.ended_before else None,
            "sync_run_id": str(sync_run_id),
            "pages": self.pages,
            "rows_scanned": self.rows_scanned,
            "rows_upserted": self.rows_upserted,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rows_skipped": self.rows_skipped,
            "rows_errored": self.rows_errored,
            "cursor_high_watermark": {
                "occurred_at": ts.isoformat() if ts is not None else None,
                "activity_id": tiebreak,
            },
            "error_samples": self.error_samples,
        }


# ── main entrypoint ──────────────────────────────────────────────────────


async def run_backfill_facts_from_mirror(
    *,
    job_id: Any,
    params: dict[str, Any],
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Job handler body. Returns a summary dict for ``BackgroundJob.result``."""
    request = parse_request(params)

    # Mapper lookup is strict — a typo / unregistered tuple fails the job
    # at startup rather than burning a batch and discovering the mapping is
    # missing halfway through.
    mapping = MirrorToFactMapper.default().for_table(
        request.app_id, request.source_table, request.activity_type
    )
    if mapping.target_fact != SUPPORTED_TARGET_FACT:
        # Belt + suspenders: the admin endpoint already enforces this, but a
        # malformed scheduled job or replay payload could route here without
        # passing through the endpoint. Refuse loudly rather than write into
        # an unexpected fact table.
        raise ValueError(
            f"backfill-facts-from-mirror only supports target_fact="
            f"{SUPPORTED_TARGET_FACT!r}, got {mapping.target_fact!r} for "
            f"mapping {mapping.key!r}"
        )

    scan_spec = _scan_spec_for(request.source_table)

    # Open a dedicated session for the backfill log row + sync_run row so
    # they survive even if a per-batch transaction rolls back. ``sync_run_id``
    # on the fact rows references analytics.log_crm_source_sync; we create
    # one row up front so the FK is satisfied and operators can join fact
    # rows back to the driving job via that row's job_id.
    started_at = datetime.now(timezone.utc)
    counters = _BackfillCounters()
    high_watermark: tuple[datetime | None, str | None] = (None, None)
    log_row_id: uuid.UUID | None = None
    sync_run_id: uuid.UUID | None = None

    try:
        async with async_session() as bookkeeping:
            async with bookkeeping.begin():
                sync_run = LogCrmSourceSync(
                    tenant_id=tenant_id,
                    app_id=request.app_id,
                    source_system="backfill",
                    source_family="calls",
                    sync_mode="backfill",
                    status="running",
                    requested_by_user_id=user_id,
                    watermark_from=(
                        request.started_after.isoformat()
                        if request.started_after else None
                    ),
                    watermark_to=(
                        request.ended_before.isoformat()
                        if request.ended_before else None
                    ),
                    started_at=started_at,
                    details={
                        "jobType": "backfill-facts-from-mirror",
                        "sourceTable": request.source_table,
                        "activityType": request.activity_type,
                    },
                    job_id=_coerce_uuid(job_id),
                    is_scheduled_run=False,
                )
                bookkeeping.add(sync_run)
                await bookkeeping.flush()
                sync_run_id = sync_run.id

                log_row = LogFactPopulationRun(
                    tenant_id=tenant_id,
                    app_id=request.app_id,
                    job_type="backfill-facts-from-mirror",
                    status="running",
                    started_at=started_at,
                    metadata_={
                        "mapping_key": list(mapping.key),
                        "sync_run_id": str(sync_run.id),
                    },
                )
                bookkeeping.add(log_row)
                await bookkeeping.flush()
                log_row_id = log_row.id

        assert sync_run_id is not None  # narrowing for the type checker

        # Driver loop: keyset cursor over the mirror, project + upsert per
        # batch, commit per batch.
        high_watermark = await _drive_backfill(
            job_id=job_id,
            request=request,
            tenant_id=tenant_id,
            mapping=mapping,
            scan_spec=scan_spec,
            sync_run_id=sync_run_id,
            counters=counters,
        )

        await _finalize_log_row(
            log_row_id=log_row_id,
            sync_run_id=sync_run_id,
            started_at=started_at,
            status="success",
            error_message=None,
            counters=counters,
            request=request,
            high_watermark=high_watermark,
        )
    except Exception as exc:
        if log_row_id is not None and sync_run_id is not None:
            # The bookkeeping write itself can fail (DB blip during the
            # cleanup tx). If it does, log + swallow so the original job
            # error surfaces — operators need to see the root cause, not
            # a confusing "finalize_log_row failed" trace from the worker.
            try:
                await _finalize_log_row(
                    log_row_id=log_row_id,
                    sync_run_id=sync_run_id,
                    started_at=started_at,
                    status="error",
                    error_message=f"{type(exc).__name__}: {exc}",
                    counters=counters,
                    request=request,
                    high_watermark=high_watermark,
                )
            except Exception:
                _log.exception(
                    "failed to finalize backfill log row; "
                    "surfacing original job error"
                )
        _log.exception(
            "backfill-facts-from-mirror failed key=%s sync_run_id=%s",
            mapping.key,
            sync_run_id,
        )
        raise

    return {
        "mapping_key": list(mapping.key),
        "sync_run_id": str(sync_run_id),
        "pages": counters.pages,
        "rows_scanned": counters.rows_scanned,
        "rows_upserted": counters.rows_upserted,
        "rows_inserted": counters.rows_inserted,
        "rows_updated": counters.rows_updated,
        "rows_skipped": counters.rows_skipped,
        "rows_errored": counters.rows_errored,
    }


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# ── batching ─────────────────────────────────────────────────────────────


async def _drive_backfill(
    *,
    job_id: Any,
    request: BackfillRequest,
    tenant_id: uuid.UUID,
    mapping: MirrorToFactMapping,
    scan_spec: _MirrorScanSpec,
    sync_run_id: uuid.UUID,
    counters: _BackfillCounters,
) -> tuple[datetime | None, str | None]:
    """Drive the keyset cursor; each batch in its own transaction.

    Returns the (timestamp, tiebreaker) high watermark of the last seen
    mirror row — caller stores it in ``log_fact_population_run.metadata``
    so a partial run is resumable from that point.
    """
    from app.services.job_worker import (
        JobCancelledError,
        is_job_cancelled,
        update_job_progress,
    )

    last_ts: datetime | None = None
    last_tiebreak: str | None = None

    while True:
        if await is_job_cancelled(job_id, tenant_id=tenant_id):
            raise JobCancelledError("Backfill job cancelled")

        async with async_session() as batch_session:
            async with batch_session.begin():
                mirror_rows = await _fetch_batch(
                    batch_session,
                    request=request,
                    tenant_id=tenant_id,
                    scan_spec=scan_spec,
                    after=(last_ts, last_tiebreak),
                )
                if not mirror_rows:
                    break

                counters.pages += 1
                counters.rows_scanned += len(mirror_rows)

                # Filter out rows that the mapper would reject (e.g. blank
                # activity_id, projection error) up front so a single bad row
                # doesn't taint the whole batch's upsert. We surface the
                # error sample on the log row.
                projected: list[dict[str, Any]] = []
                for row in mirror_rows:
                    try:
                        fact_row = mapping.project(row, sync_run_id=sync_run_id)
                    except MappingProjectionError as exc:
                        counters.rows_errored += 1
                        message = str(exc)
                        counters.last_error = message[:500]
                        if len(counters.error_samples) < 5:
                            counters.error_samples.append(
                                {
                                    "activity_id": getattr(
                                        row, "activity_id", None
                                    ),
                                    # Truncate so the metadata JSONB stays
                                    # bounded even on tracebacks-as-messages.
                                    "error": message[:500],
                                }
                            )
                        continue
                    if not fact_row.get("source_activity_id"):
                        # Defense in depth: mapper currently writes the column
                        # but if a future mapping forgets to, the upsert would
                        # explode on NOT NULL. Skip and surface.
                        counters.rows_skipped += 1
                        continue
                    fact_row["id"] = uuid.uuid4()
                    fact_row["tenant_id"] = row.tenant_id
                    fact_row["app_id"] = row.app_id
                    projected.append(fact_row)

                if projected:
                    inserted, updated = await _upsert_fact_rows(
                        batch_session, rows=projected
                    )
                    counters.rows_upserted += inserted + updated
                    counters.rows_inserted += inserted
                    counters.rows_updated += updated

                # Advance the cursor to the last row of this batch (rows are
                # ordered by (timestamp, activity_id) ascending — the last
                # one is the high-watermark of the page).
                tail = mirror_rows[-1]
                last_ts = tail.call_started_at or tail.created_on
                last_tiebreak = tail.activity_id

        # Per-batch progress ping; bounded total because we don't know the
        # row count up front and computing it would double the DB cost.
        # Use "rows scanned" as a monotonically increasing progress signal
        # against a sentinel total (rows_scanned + batch_size) so the bar
        # advances without claiming a misleading ETA.
        await update_job_progress(
            job_id,
            counters.rows_scanned,
            counters.rows_scanned + request.batch_size,
            f"Backfilled {counters.rows_upserted} rows across "
            f"{counters.pages} batch(es)",
            sync_run_id=str(sync_run_id),
        )

    return (last_ts, last_tiebreak)


async def _fetch_batch(
    session: AsyncSession,
    *,
    request: BackfillRequest,
    tenant_id: uuid.UUID,
    scan_spec: _MirrorScanSpec,
    after: tuple[datetime | None, str | None],
) -> list[Any]:
    """Keyset-paginated SELECT over the mirror.

    Ordering is ``(coalesce(call_started_at, created_on), activity_id)`` so
    cursors are deterministic even if multiple mirror rows share a timestamp.
    """
    ts_col = scan_spec.timestamp_column
    tb_col = scan_spec.tiebreaker_column
    model = scan_spec.model

    stmt = select(model).where(
        model.tenant_id == tenant_id,
        model.app_id == request.app_id,
    )
    if request.started_after is not None:
        stmt = stmt.where(ts_col >= request.started_after)
    if request.ended_before is not None:
        stmt = stmt.where(ts_col < request.ended_before)

    last_ts, last_tiebreak = after
    if last_ts is not None and last_tiebreak is not None:
        # Strict keyset: (ts, tb) > (last_ts, last_tiebreak).
        stmt = stmt.where(
            and_(
                ts_col >= last_ts,
                # The OR captures rows with the same timestamp but a higher
                # tiebreaker. Otherwise rows that share a timestamp with the
                # high-watermark would be dropped between batches.
                ((ts_col > last_ts) | (tb_col > last_tiebreak)),
            )
        )

    stmt = stmt.order_by(ts_col, tb_col).limit(request.batch_size)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _upsert_fact_rows(
    session: AsyncSession, *, rows: list[dict[str, Any]]
) -> tuple[int, int]:
    """ON CONFLICT DO UPDATE; returns (rows_inserted, rows_updated).

    Postgres' ``xmax`` system column is 0 for a row freshly inserted and
    non-zero for a row that an UPDATE has touched in the current statement.
    Reading it back with ``RETURNING`` lets us distinguish new vs. replayed
    rows in a single round-trip — important because operators want to see
    whether a replay actually moved anything.

    Idempotency conflict key is ``(tenant_id, app_id, source_activity_id,
    activity_type)`` — same key Phase 3 same-tx writes use.
    """
    if not rows:
        return (0, 0)

    from sqlalchemy import text as _text

    # ``xmax`` is 0 on a freshly INSERT'd row and non-zero on a row the
    # DO UPDATE branch touched. Pulling it out via RETURNING lets us split
    # inserted vs. updated counts in a single statement.
    stmt = pg_insert(FactLeadActivity).values(rows)
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            FactLeadActivity.tenant_id,
            FactLeadActivity.app_id,
            FactLeadActivity.source_activity_id,
            FactLeadActivity.activity_type,
        ],
        set_={
            "activity_subtype": excluded.activity_subtype,
            "source_event_code": excluded.source_event_code,
            "occurred_at": excluded.occurred_at,
            "actor_type": excluded.actor_type,
            "actor_id": excluded.actor_id,
            "actor_label": excluded.actor_label,
            "lead_id": excluded.lead_id,
            "attributes": excluded.attributes,
            "sync_run_id": excluded.sync_run_id,
        },
    ).returning(_text("xmax"))

    result = await session.execute(stmt)
    inserted = 0
    updated = 0
    for (xmax,) in result.all():
        # xmax = 0 → freshly inserted; non-zero → existing row was UPDATE'd
        # by the DO UPDATE branch. Cast through int() to dodge driver-specific
        # numeric types (some adapters return Decimal here).
        try:
            xmax_int = int(xmax or 0)
        except (TypeError, ValueError):
            xmax_int = 0
        if xmax_int == 0:
            inserted += 1
        else:
            updated += 1
    return (inserted, updated)


# ── log row finalization ─────────────────────────────────────────────────


async def _finalize_log_row(
    *,
    log_row_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    started_at: datetime,
    status: str,
    error_message: str | None,
    counters: _BackfillCounters,
    request: BackfillRequest,
    high_watermark: tuple[datetime | None, str | None],
) -> None:
    """Update the log row + close out the sync_run row in one transaction.

    Both rows live in their own session (separate from the per-batch
    sessions) so a per-batch failure doesn't roll back the audit trail.
    """
    completed_at = datetime.now(timezone.utc)
    duration_ms = max(
        0.0, (completed_at - started_at).total_seconds() * 1000.0
    )

    async with async_session() as session:
        async with session.begin():
            log_row = await session.get(LogFactPopulationRun, log_row_id)
            if log_row is not None:
                log_row.status = status
                log_row.completed_at = completed_at
                log_row.duration_ms = duration_ms
                log_row.rows_inserted = counters.rows_inserted
                log_row.rows_updated = counters.rows_updated
                log_row.error_message = error_message
                log_row.metadata_ = counters.to_metadata(
                    request=request,
                    cursor_high_watermark=high_watermark,
                    sync_run_id=sync_run_id,
                )

            sync_run = await session.get(LogCrmSourceSync, sync_run_id)
            if sync_run is not None:
                sync_run.status = "completed" if status == "success" else "failed"
                sync_run.completed_at = completed_at
                sync_run.records_scanned = counters.rows_scanned
                sync_run.records_upserted = counters.rows_upserted
                sync_run.records_failed = counters.rows_errored
                if error_message is not None:
                    sync_run.error_message = error_message
                sync_run.details = dict(sync_run.details or {}, **{
                    "pages": counters.pages,
                    "rowsInserted": counters.rows_inserted,
                    "rowsUpdated": counters.rows_updated,
                })


__all__ = [
    "BackfillRequest",
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
    "MIN_BATCH_SIZE",
    "SUPPORTED_TARGET_FACT",
    "parse_request",
    "run_backfill_facts_from_mirror",
]
