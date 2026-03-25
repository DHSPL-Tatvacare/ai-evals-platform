# AI Evals Job Polling V2 - Robust, DRY, Incremental Plan

## Executive Summary

This plan upgrades the current DB-backed job worker and frontend polling flow to be safer and cleaner at internal scale (20-30 users), without changing existing product behavior.

What changes:
- stronger state guarantees,
- atomic queue claim,
- less duplicated logic,
- safer API responses,
- cleaner polling abstractions,
- better operations visibility.

What does not change:
- no distributed queue migration,
- no FE contract break,
- no workflow redesign.

---

## Goals and Constraints

### Goals

1. Prevent duplicate job execution and terminal-state races.
2. Make job lifecycle logic explicit and centrally enforced.
3. Remove repeated status/polling/redaction logic across files.
4. Preserve current FE/BE behavior for progress, statuses, and redirects.
5. Improve maintainability and operational confidence.

### Constraints

1. Keep current architecture (FastAPI + Postgres + in-process worker).
2. Keep existing API shape consumed by frontend.
3. Keep current status vocabulary (`queued`, `running`, `completed`, `failed`, `cancelled`).
4. Multi-node/distributed execution is out of scope.

---

## Compatibility Invariants (Hard Requirements)

1. `progress.current`, `progress.total`, `progress.message`, and `progress.run_id` behavior remains intact.
2. Existing submit/poll/cancel endpoints remain available.
3. Existing run pages continue to update exactly as they do now.
4. Existing job types and runner mapping remain intact.

---

## Core Design Principles

1. **Single source of truth:** job state transitions are defined once and reused everywhere.
2. **Idempotent writes:** terminal updates are compare-and-set, never blind overwrites.
3. **Atomic claim:** queue claim must be one transactional primitive.
4. **Policy over ad hoc logic:** polling, redaction, and recovery are driven by shared policy constants.
5. **Additive refactor:** introduce helpers first, then migrate call sites; avoid broad rewrites.

---

## Reusable Building Blocks (Anti-Duplication by Design)

## Backend building blocks

1. `job_states.py` (or `jobs/state_machine.py`)
   - allowed transitions table
   - helpers: `is_terminal`, `can_transition`, `terminal_states`, `active_states`

2. `job_repository.py` (or `jobs/repository.py`)
   - `claim_next_queued_job()` using atomic SQL pattern
   - guarded transition methods (`mark_running`, `mark_completed`, `mark_failed`, `mark_cancelled`)
   - row-count/idempotency return contract

3. `job_sanitizer.py`
   - canonical sensitive-key redaction for API responses
   - reusable for list/get endpoints

4. `job_progress.py`
   - canonical progress payload builder and merge helper
   - standard keys (`current`, `total`, `message`, `run_id`, `listing_id`, etc.)

5. `job_config.py` (or config section)
   - polling intervals, stale policy mode, retention days, feature flags

## Frontend building blocks

1. `jobStatus.ts`
   - `isTerminalJobStatus`, `isActiveJobStatus` shared helpers

2. `jobPollingPolicy.ts`
   - shared intervals, jitter, retry/backoff constants

3. `jobTrackerPolicy.ts`
   - tracked-job TTL and dedupe policy

These modules are the key mechanism to avoid repeated logic and code drift.

---

## Canonical Lifecycle Contract

Allowed transitions only:
- `queued -> running`
- `queued -> cancelled`
- `running -> completed`
- `running -> failed`
- `running -> cancelled`

Rules:
1. Terminal states are immutable unless explicitly doing administrative recovery.
2. Worker completion/failure updates must include `WHERE status='running'`.
3. Cancel endpoint must be idempotent and transition-aware.

---

## Implementation Phases

## Phase 0 - Baseline and Guard Rails

### Objective

Prepare safe rollout without behavior risk.

### Changes

1. Add config toggles for new claim path and new transition guards.
2. Add structured logs around existing transitions (before refactor).
3. Document baseline behavior and known edge cases.

### Acceptance

1. No runtime behavior change.
2. Toggle framework is in place for safe fallback.

---

## Phase 1 - API Hardening and Sensitive Data Safety

### Objective

Make the API contract stricter and safer while preserving FE behavior.

### Changes

1. Server-authoritative job creation
   - ignore client-provided `status` and `progress` on submit
   - default server values only

2. Job type validation
   - reject unknown `job_type` at submit time
   - validation source shared with handler registry or allowlist derived from it

3. Canonical response redaction
   - central redactor for `params`
   - redact keys like `api_key`, `kaira_auth_token`, `service_account_path`, `authorization`, `token`, `secret`, and variants

### Target files

- `backend/app/routes/jobs.py`
- `backend/app/schemas/job.py`
- `backend/app/services/.../job_sanitizer.py` (new)

### Acceptance

1. FE job submit/list/get still works unchanged.
2. Sensitive param values are not exposed in API responses.
3. Unknown job type returns clear 4xx.

---

## Phase 2 - Atomic Claim and Transition Guarding (Critical)

### Objective

Eliminate duplicate claim risk and terminal overwrite races.

### Changes

1. Introduce atomic claim primitive in repository
   - claim and mark-running in one transaction
   - Postgres claim pattern: lock oldest queued row with `FOR UPDATE SKIP LOCKED`

2. Migrate worker to repository methods
   - no ad hoc status writes in worker loop

3. Guard terminal updates
   - completion/failure writes are compare-and-set (`status='running'`)
   - if no rows updated, treat as idempotent already-terminal outcome

4. Cancel route transition safety
   - uses same transition helper/repository
   - deterministic response for already-terminal jobs

### Target files

- `backend/app/services/job_worker.py`
- `backend/app/routes/jobs.py`
- `backend/app/services/.../job_states.py` (new)
- `backend/app/services/.../job_repository.py` (new)

### Acceptance

1. No duplicate execution in dual-worker simulation.
2. No cancel-vs-complete state flip.
3. Transition attempts are auditable in logs.

---

## Phase 3 - Recovery and Queue Hygiene

### Objective

Make restart behavior deterministic and queue performance predictable.

### Changes

1. Recovery policy modes (configurable)
   - mode A: strict single-worker restart -> pre-existing `running` treated stale
   - mode B: threshold-based stale timeout

2. Queue/index cleanup
   - composite index for claim query (`status`, `created_at`)
   - evaluate index on `eval_runs.job_id` for reconciliation paths

3. Adaptive worker sleep policy
   - short sleep when work exists
   - longer sleep when idle

4. Optional retention cleanup for old terminal jobs
   - configurable retention days

### Target files

- `backend/app/services/job_worker.py`
- `backend/app/models/job.py`
- `backend/app/config.py`
- (migration file if needed)

### Acceptance

1. No indefinite stale `running` jobs post-restart.
2. Claim query remains efficient with growing job table.
3. No FE behavior regression.

---

## Phase 4 - Frontend Polling Consolidation (No UX Change)

### Objective

Reduce polling-related duplication and accidental noise.

### Changes

1. Shared status/polling policy constants
   - move repeated terminal checks to shared helper

2. Abort behavior policy
   - add optional `cancelOnAbort` policy in polling utility
   - preserve current default; opt out for lifecycle-driven unmount paths where backend cancel is not desired

3. Tracked-job hygiene
   - TTL cleanup and dedupe in tracker store
   - prevent stale entries from generating extra polls/toasts

4. Notification dedupe
   - ensure exactly-once toast behavior per tracked job terminal event

### Target files

- `src/services/api/jobPolling.ts`
- `src/hooks/usePoll.ts`
- `src/stores/jobTrackerStore.ts`
- `src/components/JobCompletionWatcher.tsx`
- `src/utils/...` status/policy helpers (new)

### Acceptance

1. Existing UI flow remains identical.
2. Reduced duplicate polling/notifications.
3. No accidental backend cancels from normal unmount cases where opt-out is applied.

---

## Phase 5 - Observability and Operational Runbook

### Objective

Make incidents easy to detect and diagnose.

### Changes

1. Structured lifecycle logs
   - events: submit, claim, start, progress, cancel-request, cancelled, failed, completed, recovered
   - fields: `job_id`, `job_type`, `run_id`, latency, actor/source

2. Lightweight queue health endpoint (internal)
   - queued count
   - running count
   - oldest queued age
   - stale-running count

3. Runbook
   - triage flow for stuck jobs, race anomalies, and restart behavior
   - exact commands/queries for diagnosis

### Target files

- `backend/app/services/job_worker.py`
- `backend/app/routes/jobs.py` (or dedicated internal health route)
- `docs/plans/ai-evals-job-polling-v2/runbook.md` (new)

### Acceptance

1. Typical queue incidents diagnosable in <5 minutes.
2. Less ad hoc DB digging for routine failures.

---

## Anti-Duplication Rules (Mandatory During Implementation)

1. No direct status `update(Job)` calls outside repository helper(s).
2. No duplicated terminal-state sets in FE files; use shared helpers.
3. No endpoint-local redaction logic; always call shared sanitizer.
4. No ad hoc progress payload dictionaries in runners; use shared builder.
5. No duplicated poll intervals/backoff values scattered across components.

Code review checklist should explicitly enforce these rules.

---

## Verification Strategy

Because the repo currently relies heavily on manual verification, use a two-layer strategy:

1. **Deterministic backend checks**
   - dual-worker claim simulation
   - cancel-vs-complete race simulation
   - restart recovery scenarios

2. **Manual UI checks (existing workflow)**
   - submit each job type
   - observe progress and redirect behavior
   - cancel from run detail
   - verify terminal notifications and run reconciliation

Minimum required scenarios:
1. happy path completion
2. queued cancellation
3. running cancellation
4. runner exception -> failed
5. restart during running

---

## Rollout and Rollback

### Rollout order

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5

### Rollback strategy

1. Keep new claim path and guarded transition logic behind feature toggles for one release window.
2. Keep old behavior reachable for emergency rollback.
3. Preserve DB compatibility in each phase (no destructive schema assumptions).

---

## Decision Lock (No-Ambiguity Defaults)

All policy defaults for implementation are locked in:

- `docs/plans/ai-evals-job-polling-v2/decision-lock.md`

Implementation must follow that file as the authoritative source for:

1. recovery mode defaults,
2. abort/cancel semantics,
3. sensitive-key redaction set,
4. feature-flag defaults,
5. legacy-path removal gate.

---

## Definition of Done (V2)

V2 is done when all criteria hold:

1. Atomic claim is live and proven race-safe.
2. Transition state machine is centralized and used by worker + routes.
3. Sensitive params are consistently redacted in API responses.
4. Recovery behavior is deterministic and configurable.
5. FE polling logic is consolidated with shared status/policy helpers.
6. No FE/BE contract regressions for job updates/progress.
7. Runbook and queue health visibility are in place.

---

## Why This Plan Is the Right Fit for Your Scenario

1. It is pragmatic for internal scale and current architecture.
2. It materially improves correctness and robustness.
3. It reduces long-term maintenance cost through shared abstractions.
4. It avoids platform churn while still raising reliability standards.
