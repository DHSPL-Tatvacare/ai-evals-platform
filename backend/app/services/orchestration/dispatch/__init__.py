"""Provider-agnostic dispatch reconciliation — two paths, one idempotent funnel.

Two ingress paths converge here:

  1. Poller (``reconcile-voice-dispatch`` job, capability-parameterized) —
     PRIMARY. Pulls terminal status from the provider's status API on a
     schedule; the sole correctness guarantee, independent of inbound webhooks.
  2. Provider webhooks (``orchestration_webhooks`` route) — SECONDARY/real-time,
     and the sole path for providers with no status API (e.g. WATI).

Both call the adapter's shared ``reconcile_execution`` → ``apply_terminal_event``,
so persistence is identical regardless of how the call's end was discovered.
Idempotency: the parent's ``provider_terminal`` guard stops once terminal, and
the outcome child's ``(tenant_id, recipient_id, idempotency_key)`` unique
constraint dedupes — the key is derived from the per-execution id in one shared
function so the two paths can never diverge.
"""
