# Job Polling V2 - Pattern Catalog

This document defines reusable implementation patterns so Phase work stays DRY and consistent.

## 1) Transition-Guard Pattern

Use one shared transition function for every status change.

Requirements:
- all transitions validated against one transition map,
- all writes use compare-and-set semantics,
- all blocked transitions emit structured logs.

Use in:
- worker finalization,
- cancel route,
- recovery routines.

## 2) Atomic-Claim Pattern

Queue claim must be one transactional primitive.

Requirements:
- claim oldest queued row,
- lock to prevent double claim,
- set `running` + `started_at` in same transaction,
- return claimed row directly.

Use in:
- worker dequeue loop only.

## 3) Idempotent Terminal Pattern

Terminal updates are safe to retry.

Requirements:
- completion/failure/cancel updates target `status='running'` (or `queued` for direct queued cancel),
- if row-count is zero, return deterministic already-terminal result,
- never overwrite one terminal with another.

Use in:
- worker completion/failure,
- cancel endpoint.

## 4) Sanitized-Serialization Pattern

No endpoint does local redaction logic.

Requirements:
- single sanitizer utility,
- key-based and heuristic redaction,
- shared use in list/get responses,
- no sensitive value appears in API responses.

Use in:
- `/api/jobs`, `/api/jobs/{id}`.

## 5) Progress-Envelope Pattern

Progress payload format is built by one helper.

Requirements:
- canonical keys (`current`, `total`, `message`, optional `run_id`, `listing_id`),
- additive metadata only,
- no ad hoc progress dicts scattered in runners.

Use in:
- voice runner,
- batch runner,
- adversarial runner,
- worker fallback updates.

## 6) Polling-Policy Pattern (Frontend)

Polling behavior comes from shared constants/helpers.

Requirements:
- shared terminal/active status helpers,
- shared interval/backoff/jitter policy,
- explicit `cancelOnAbort` policy,
- no duplicated interval literals across pages.

Use in:
- `jobPolling.ts`,
- `usePoll.ts`,
- run-detail watchers,
- global completion watcher.

## 7) Exactly-Once Notification Pattern

User notification is emitted once per terminal event.

Requirements:
- dedupe token (`job_id + terminal_status`),
- stale tracked-job cleanup,
- suppress duplicate toasts across watchers.

Use in:
- global job completion watcher.

## 8) Recovery-Policy Pattern

Startup recovery behavior is explicit and configurable.

Requirements:
- policy mode documented in config,
- recovery action logged per affected job,
- run/job reconciliation path deterministic.

Use in:
- worker startup initialization.

---

## Code Review Gate

A PR in this workstream is incomplete if any of these are true:

1. New direct status SQL write bypasses transition helper.
2. Endpoint includes custom redaction code instead of sanitizer.
3. New polling loop introduces hardcoded interval constants.
4. Progress payload shape diverges from canonical envelope.
5. Terminal-state overwrite remains possible in race paths.
