# Kaira Batch Evals: Skip Previously Processed Thread IDs

## Goal

Add an opt-in way to skip thread IDs that were already evaluated, only for Kaira batch eval runs, without disrupting existing execution flow.

## Core Decision

- Do not add a new table.
- Reuse existing `thread_evaluations` as the processed-ID ledger.
- Identify processed IDs by joining `thread_evaluations` -> `eval_runs` and filtering by `eval_runs.app_id = 'kaira-bot'`.

This gives us a durable, queryable source of truth with no migration or backfill logic.

## Scope

- In scope:
  - Kaira batch job flow (`evaluate-batch` -> `batch_runner`) only.
  - New overlay option: `skip previously processed conversations`.
  - Default behavior remains unchanged (process all).
- Out of scope:
  - Voice Rx or adversarial flows.
  - New DB tables.
  - Legacy/fallback compatibility layers.

## Processed Definition

A thread is considered "already processed" if **any** prior `thread_evaluations` row exists for that thread ID under `app_id = 'kaira-bot'`.

Rationale:
- Simpler and deterministic.
- Works immediately for all new runs after this change.
- Avoids run-status branching and additional complexity.

## UX Contract

- New checkbox in Kaira batch overlay: `Skip previously processed conversations`.
- Default: unchecked (off).
- When off: exact current behavior.
- When on: lookup performed before execution; already-processed thread IDs are removed from the run set.

## Expected Outcome

- Re-running the same Kaira thread set with the option enabled will process only unseen thread IDs.
- Existing parallelism, cancellation, progress, and result persistence flows remain intact.
