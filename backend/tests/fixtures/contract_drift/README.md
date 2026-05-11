# Contract drift fixtures

Shared JSON fixtures parsed by **both** the backend Pydantic schemas and the
frontend Zod schemas. They lock the four node types that historically drifted
(`logic.split`, `logic.wait`, `source.cohort_query`, `crm.send_wati`) to a
canonical shape that both sides must accept (or reject) the same way.

## Files

- `*.valid_draft.json` — a partial-but-legal draft. Both sides MUST accept it.
- `*.invalid_fabricated_key.json` — a fabricated extra key. Both sides MUST reject.

Each JSON has the shape:

```json
{
  "node_type": "<id>",
  "config": { ... }
}
```

The schemas are validated against `config` alone — `node_type` is metadata
for the test harness.

## Why

Phase 14 / Phase D ships hand-written Zod mirrors of the backend Pydantic
contracts. Without a shared fixture set, drift gets noticed only when the
publish path rejects a save. These fixtures fail fast in CI on both sides.

Phase 16 codegen (OpenAPI → Zod) will eventually replace the mirror, but
until then these fixtures are the guardrail.
