# Job Polling V2 - Decision Lock (Execution Defaults)

This file locks policy choices so implementation can proceed without ambiguity.

## Locked Decisions

| Decision Area | Locked Default | Why This Default | Enforced In | Rollback/Override |
|---|---|---|---|---|
| Startup recovery mode | `single_worker_strict` | Deployment is single worker/process for internal use; strict mode prevents stale `running` jobs after restart and reduces operator confusion. | Worker startup recovery policy | `JOB_RECOVERY_MODE=timeout` |
| Startup timeout fallback value | `15m` (only when mode = `timeout`) | Keeps current behavior available as fallback while strict remains default. | Worker recovery config | `JOB_STALE_TIMEOUT_MINUTES` |
| Poll abort behavior (`submitAndPollJob`) | `cancelOnAbort=true` (default) | Preserves current behavior and avoids regressions in evaluator cancel flows that rely on abort-triggered backend cancellation. | `jobPolling.ts` default options | Per-call `cancelOnAbort=false` |
| Poll abort behavior for lifecycle unmount/navigation-only paths | Explicitly set `cancelOnAbort=false` | Prevents accidental backend cancel when UI unmounts but user did not intend cancellation. | Selected FE call sites only | N/A (call-site policy) |
| Sensitive params redaction dictionary | Exact key set below + heuristic suffix match | Prevents secrets/token leakage while keeping non-sensitive params visible for debugging. | Shared backend sanitizer | Env var to extend list if needed |
| Queue health endpoint | Disabled by default; enable only via env | Avoids accidental exposure; can be turned on when operations need visibility. | Backend route registration | `JOB_HEALTH_ENDPOINT_ENABLED=true` |
| Queue health endpoint auth | Aggregate-only payload, no per-job params; optional static header token if enabled outside trusted network | Keeps implementation simple for internal use while avoiding data leakage. | Health endpoint middleware/route | `JOB_HEALTH_ENDPOINT_TOKEN` optional |
| Feature flags for claim/transition path | `USE_ATOMIC_CLAIM=true`, `ENFORCE_TRANSITIONS=true` from first release | Core reliability controls should be on by default; legacy path remains temporary fallback only. | Worker/repository config | set either flag false |
| Legacy path removal gate | Remove old claim/transition path after **14 consecutive days** with **0 critical incidents** and successful race/recovery checklist | Objective and time-bound cutoff avoids indefinite dual-path maintenance. | Workstream completion checklist | Extend one 7-day window if incident occurs |

## Locked Sensitive-Key Redaction Set

Redact values for keys (case-insensitive):

- `api_key`
- `openai_api_key`
- `gemini_api_key`
- `kaira_auth_token`
- `auth_token`
- `authorization`
- `bearer_token`
- `access_token`
- `refresh_token`
- `service_account_path`
- `service_account_json`
- `client_secret`
- `secret`
- `password`

Heuristic redaction rule (case-insensitive):

- Any key ending with `_token`, `_secret`, `_password`, `_api_key` is redacted.

Representation rule:

- Redacted value should be stable marker string: `"[REDACTED]"`.

## Locked Status Transition Rules

Allowed:

- `queued -> running`
- `queued -> cancelled`
- `running -> completed`
- `running -> failed`
- `running -> cancelled`

Disallowed:

- Any terminal-to-terminal transition.
- Any transition out of terminal states except explicit administrative recovery routine.

## Locked Acceptance Gates (Must Pass Before Phase Closure)

1. No duplicate job execution in dual-worker simulation.
2. No terminal state flip in cancel-vs-complete race simulation.
3. No sensitive values in `/api/jobs` and `/api/jobs/{id}` responses.
4. Existing FE flows still show progress and run redirects correctly.
5. Recovery after restart leaves no stale `running` jobs in strict mode.
