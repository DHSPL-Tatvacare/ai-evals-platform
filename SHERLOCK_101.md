# Sherlock 101

The single reference for *how Sherlock is wired together and how to add things to it*. If you find yourself explaining Sherlock architecture in a chat more than once, update this file instead.

This describes **Sherlock v3** — the live runtime under `backend/app/services/sherlock_v3/`. The older v2 design (a single `chat_engine` agent with a scratchpad, `sql_agent`, `tool_handlers`, and a `sherlock_turn_events` log) is retired. The chart pipeline (`result_set_typer → chartability_gate → chart_type_picker → vega_lite_emitter`) and the manifests survive from v2 and are still used by the v3 data specialist.

---

## 1. What Sherlock is

A **constrained analytics agent**, scoped to one app at a time (`kaira-bot`, `voice-rx`, `inside-sales`), built on the **OpenAI Agents SDK**.

- One **supervisor** agent runs the turn. It decomposes the question and dispatches **specialists** registered as tools (`as_tool`).
- Specialists do one job each and return a typed `SpecialistResult`. The data specialist writes SQL, which is validated by a **bouncer** and rendered through a **deterministic Python chart pipeline**.
- Everything the turn does is emitted as a stream of **typed Parts** (`sherlock_parts`), persisted and pushed to the frontend over SSE. The frontend renders Parts; it never infers chart type or stitches state.

The agents are LLMs. The bouncer, the chart pipeline, and the Part stream are code. The boundary is strict.

Canonical rule (also in CLAUDE.md): **all** agent orchestration on this platform follows the supervisor + specialist + Agents-SDK pattern. No bespoke chat engines.

---

## 2. End-to-end request flow

```
POST /api/report-builder/v2/chat/stream            [routes/report_builder.py]
   │  resolve session → get_or_create_turn(status='queued') → asyncio.create_task
   ▼
run_chat_turn(...)                                  [sherlock_v3/turn_orchestrator.py]
   │  create assistant message · mark turn active · build PartEmitter + SherlockTurnContext
   ▼
run_turn(user_message, ctx)                         [sherlock_v3/runtime.py]
   │  get_sherlock_azure_client(analytics_supervisor) → (client, model)   [sherlock_v3/azure_client.py]
   │  compute grounding (top-k verified queries)     [sherlock_v3/grounding.py]
   │  build_supervisor(...) with specialists as_tool [sherlock_v3/supervisor.py]
   ▼
Runner.run_streamed(supervisor, ..., previous_response_id)   (Agents SDK)
   │  for each SDK event → _emit_part_for_sdk_event → ctx.emitter.emit(<Part>)
   │     supervisor calls a specialist → SubtaskPart(running→completed|error)
   │       data_specialist.submit_sql → bouncer → SQL → chart pipeline → ToolPart + ChartPart + EvidencePart
   ▼
_maybe_compact_supervisor(...)   (if cumulative tokens ≥ threshold → responses.compact())
   ▼
StepFinishPart(status, last_response_id) → mark_turn_terminal · finalize assistant message
```

Each emitted Part is (1) written to `platform.sherlock_parts` and (2) published to the live SSE queue, which `report_builder.py` formats as SSE frames. Everything after the SQL executes runs deterministically in Python — the chart picker and emitter never call an LLM.

---

## 3. The agents

Built fresh each turn in [`supervisor.py`](backend/app/services/sherlock_v3/supervisor.py) via `build_supervisor(...)`. The supervisor is one Agents-SDK `Agent` whose tools are specialists wrapped with `.as_tool(...)`.

| Specialist | File | Job |
|---|---|---|
| `query_synthesis_specialist` | [`query_synthesis_specialist.py`](backend/app/services/sherlock_v3/query_synthesis_specialist.py) | Rewrite the user message into a self-contained question, classify it (answerable / ambiguous / non-data), decompose into sub-questions each targeting a specialist. |
| `data_specialist` | [`data_specialist.py`](backend/app/services/sherlock_v3/data_specialist.py) | Answer analytics questions: emit `submit_sql`, pass it through the bouncer (pre + post), run it, type/gate/pick the chart, return rows + evidence + chart artifact. |
| `authoring_specialist` | [`authoring_specialist.py`](backend/app/services/sherlock_v3/authoring_specialist.py) | Propose orchestration canvas patches — only when a builder context is present in edit mode and the caller has `orchestration:manage`. |

The supervisor owns the loop: synthesis first, dispatch per decomposition, and on a specialist `status=error` it **re-dispatches with the prior attempts** (capped at `MAX_SPECIALIST_ATTEMPTS = 3`, see [`limits.py`](backend/app/services/sherlock_v3/limits.py)).

### Typed envelopes (do not add fields outside these)

- **Down:** `SpecialistBrief` — `{question, scope{tenant_id, app_id, user_id}, prior_attempts[], retry_hint}` ([`contracts/brief.py`](backend/app/services/sherlock_v3/contracts/brief.py)). On a retry, `prior_attempts` carries the exact failed SQL + `Verdict` + status, so the specialist acts on history.
- **Up:** `SpecialistResult` — `{kind, status, summary, attempts[], evidence[], artifacts[], meta}` ([`contracts/result.py`](backend/app/services/sherlock_v3/contracts/result.py)).

These contracts are mirrored to the frontend as a generated JSON schema (`src/features/sherlock/generated/`). Changing a contract means regenerating that schema.

---

## 4. The Part stream

Every observable thing in a turn is a **Part**. Defined in [`contracts/parts.py`](backend/app/services/sherlock_v3/contracts/parts.py) as a discriminated union on `type`:

`step_start · user_message · reasoning · assistant_text · subtask · retry · tool · chart · evidence · error · compaction · step_finish`

- **`SubtaskPart`** carries the specialist dispatch + a `state` envelope (`running → completed | error`) — the uniform lifecycle the FE reads directly.
- **`ToolPart`** is the `submit_sql` lifecycle inside the data specialist (`pending → running → completed | error`).
- **`ChartPart`** carries the Vega-Lite artifact; **`EvidencePart`** carries citation refs; **`CompactionPart`** marks a context compaction.

[`PartEmitter`](backend/app/services/sherlock_v3/emitter.py) is the only writer. `emit(part)` locks + increments `sherlock_agent_sessions.next_event_seq`, inserts a `sherlock_parts` row (`payload = part.model_dump`), and publishes `{kind: 'part_added', seq, part}` to the SSE queue. `update(part)` rewrites a part's payload in place (state transitions) and publishes `part_updated`. The frontend hydrates a turn from `sherlock_parts` and applies live `part_added`/`part_updated` frames.

---

## 5. SQL path + the bouncer

The data specialist may only reach what the per-app **semantic model** declares.

- **Semantic model** — [`semantic_models/<app>.yaml`](backend/app/services/chat_engine/semantic_models/) → `WorkbenchCatalog` ([`workbench_catalog.py`](backend/app/services/chat_engine/workbench_catalog.py)). The **curated** surface the LLM may query: tables, dimensions/time-dimensions/facts, metrics, relationships, and verified-query exemplars. This is the single source for *both* the specialist's prompt **and** the bouncer's allow-list — they read the same `WorkbenchCatalog`, so adding/removing a column moves both in lockstep.
- **SQL bouncer** — [`sql_bouncer.py`](backend/app/services/chat_engine/sql_bouncer.py). Validates `submit_sql` output **before** execution (read-only, allowed tables/columns/joins, complete GROUP BY, tenant+app scope filters, honest LIMIT, fan/chasm-trap guards) and the result **after** execution (grain match, no duplicate grain, row-limit truth, and **R12 = no all-null columns**). A failure returns a `Verdict` with a diagnostic (rule id + hint + `available_*` / `did_you_mean`) that threads into the next retry brief.
- **Chart pipeline** (deterministic, no LLM): rows → `result_set_typer` (typed result set) → `chartability_gate` (chart / kpi / summary / table / empty + reason code) → `chart_type_picker` (`bar | grouped_bar | stacked_bar | line | multi_line | area | pie`) → `vega_lite_emitter` (validated Vega-Lite v5) → `ChartPart`.

> Practical note: a column declared in the semantic model that is **never populated** for an app makes the specialist select it and the bouncer reject the all-null result (R12). Trim the semantic model to what the app actually populates. (This is exactly why `intent`/`route`/`result_verdict` were removed from `semantic_models/inside-sales.yaml`.)

---

## 6. Manifest vs semantic model

Two per-app YAMLs, different jobs. The boot validator ([`manifest_validator.py`](backend/app/services/chat_engine/manifest_validator.py)) cross-checks them against live Postgres and **refuses startup on drift**.

| | Manifest (`manifests/<app>.yaml`) | Semantic model (`semantic_models/<app>.yaml`) |
|---|---|---|
| Owns | Physical/logical truth: every physical column, chart taxonomy, `COMMENT ON COLUMN` source | The curated subset the LLM may query (`WorkbenchCatalog`) |
| Drift rule | Every declared column must exist in Postgres | Every referenced column/table must exist **in the manifest** (semantic ⊆ manifest) |
| Consumed by | Column comments, chart taxonomy, validator | Data-specialist prompt + bouncer allow-list |

Because the rule is *semantic ⊆ manifest*, **removing** a column from the semantic model can never cause drift (the set shrinks); the manifest keeps documenting the physical column.

---

## 7. Persistence tables

All under schema `platform`. Models in [`models/sherlock_runtime.py`](backend/app/models/sherlock_runtime.py).

| Table | Role |
|---|---|
| `sherlock_agent_sessions` | One row per (tenant, user, app) session. Holds `last_response_id` (the cross-turn chain), `cumulative_input_tokens`, `next_event_seq`, status. |
| `sherlock_conversation_turns` | One row per turn. `status` ∈ `queued / active / done / degraded / error / interrupted`; links the assistant message. |
| `sherlock_parts` | Append-only typed event log (the Part stream). Source of truth for FE hydration + audit. |
| `sherlock_evidence` | Citation ledger — rows referenced by `EvidencePart`. |
| `sherlock_verified_queries` | Curated SQL exemplars used for few-shot grounding. |
| `sherlock_ontology_*`, `sherlock_entity_resolvers` | Baseline ontology / entity-resolution reference data. |
| `sherlock_state` | **Dormant.** Cross-turn structured memory (`resolved_entities`/`active_filters`). Read each turn but no producer writes it — `previous_response_id` is the live memory (see §9). Pending removal. |

Retired: `sherlock_turn_events` and `analytics.log_sherlock_tool_call` were **dropped** (Alembic `0063`); the Part stream replaced them.

Every LLM call also writes one `analytics.fact_llm_generation` row (`owner_type='sherlock_turn'`, `subsystem='sherlock_v3'`). Request handlers never write fact tables directly.

---

## 8. LLM client + call sites — the Azure v1 divergence

Sherlock resolves a client per call site through [`azure_client.py`](backend/app/services/sherlock_v3/azure_client.py) → `get_sherlock_azure_client(tenant_id, call_site)`, where `call_site ∈ {analytics_supervisor, analytics_specialist}`. Resolution goes through `resolve_llm_call` (tenant `tenant_call_site_defaults` → platform fallback, with capability gating + the deployment→canonical-model mapping). **Admin Model Providers / LLM Defaults are unchanged by the item below** — only client *construction* differs, not resolution.

**Divergence (deliberate):** for an `azure_openai` credential, Sherlock builds a **plain `openai.AsyncOpenAI` pointed at Azure's v1 surface**:

```python
openai.AsyncOpenAI(base_url=f"{endpoint}/openai/v1/", default_query={"api-version": "preview"})
```

The rest of the platform (evaluators, reports, model discovery) uses the classic `openai.AzureOpenAI(azure_endpoint=..., api_version="2025-xx-xx-preview")`, which routes to `/openai/deployments/{model}/...`. That classic surface has `/responses` (so `create()` works) but **no `/responses/compact`** — the compact endpoint and newer features live only on `/openai/v1/`. Same credential, same API key, same Azure resource, same deployment string as `model`; only the URL differs. (`AzureOpenAI` is just SDK sugar for the deployment URL + an `api-version` query param; it is a subclass of `AsyncOpenAI`, so the `tuple[AsyncOpenAI, str]` return type still holds.) Unifying the whole platform onto the v1 surface is the clean end-state, deferred. See the `[[sherlock-azure-v1-surface]]` memory.

---

## 9. Cross-turn memory + compaction

**Memory = the `previous_response_id` chain.** Each turn passes `sherlock_agent_sessions.last_response_id` into `Runner.run_streamed(..., previous_response_id=...)`; the supervisor LLM therefore sees prior turns server-side and resolves references ("those reps", "that period") without the frontend stitching anything. After the turn, `turn_orchestrator` persists the new `last_response_id`. 30-day TTL: if the stored id is stale, `runtime.run_turn` replays local history with `previous_response_id=None` ([`runtime._history_input_for_context`](backend/app/services/sherlock_v3/runtime.py)). `sherlock_state` is **not** used for this.

**Compaction = explicit `responses.compact()` on the supervisor chain.** When a session grows past `CONTEXT_COMPACT_THRESHOLD_TOKENS` ([`compaction.py`](backend/app/services/sherlock_v3/compaction.py), the same value the FE context pill reads), `runtime._maybe_compact_supervisor` calls `client.responses.compact(previous_response_id=last_response_id)`, emits a `CompactionPart`, and continues the chain from the **compacted** response id. The orchestrator sees the CompactionPart and resets `cumulative_input_tokens`.

- **Supervisor only.** It owns the chain; specialists are stateless per `as_tool` call, so they have nothing to compact.
- **Requires the v1 surface** (§8). `/responses/compact` 404s on classic deployment routing.
- The Responses API's *automatic* `context_management` compaction is **not** used: it only runs under `store=false`, which is incompatible with `previous_response_id` chaining. That dead `extra_args` was removed.

---

## 10. Playbooks

### 10.1 Make a column queryable by Sherlock
1. Ensure the physical column exists (ORM + Alembic) and is declared in `manifests/<app>.yaml`.
2. Add it to `semantic_models/<app>.yaml` under the table's `dimensions` / `time_dimensions` / `facts` (a derived column declares its `expr` + `source_table`).
3. Boot. The validator confirms it exists in the manifest; the specialist prompt and bouncer allow-list pick it up from the same `WorkbenchCatalog`.
4. **Only declare columns the app actually populates** — empty columns trip bouncer R12.

### 10.2 Add a specialist
1. Build the agent in its own `*_specialist.py`, returning a `SpecialistResult`.
2. Register it in `build_supervisor` via `.as_tool(name=...)`, with an output extractor that validates the `SpecialistResult` JSON.
3. Teach the supervisor *when* to dispatch it in the supervisor prompt + the synthesis decomposition targets. Do not add a parallel orchestration path.

### 10.3 Add a chart type
Backend owns chart type. Add a branch in `chart_type_picker.py`, an emitter case in `vega_lite_emitter.py`, then extend the FE translator (`vegaLiteToRecharts.ts`) + `ChartRenderer.tsx`. Never infer chart type on the frontend.

---

## 11. What NOT to do

- **No bespoke chat engine.** Supervisor + specialists + Agents SDK is the only pattern.
- **No frontend state stitching.** The FE reads Parts; it never infers chart type, specialist lifecycle, or context.
- **No new persistence for traces.** `sherlock_agent_sessions` / `sherlock_conversation_turns` / `sherlock_parts` are it. No parallel logging tables.
- **Don't hand-edit** `COMMENT ON COLUMN`, the generated FE contract schema, or the bouncer allow-list — change the manifest / semantic model.
- **Don't declare columns the app doesn't populate** in the semantic model (R12 all-null rejections).
- **Don't put Sherlock on the classic `AzureOpenAI` client** — it loses `/responses/compact`. Use the v1 surface (§8).
- **Cross-scope is forbidden.** Always filter by `tenant_id` + `user_id` + `app_id`.

---

## 12. Test entry points

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_supervisor_compaction_unittest.py \
  backend/tests/test_sherlock_runtime_idempotency_unittest.py \
  backend/tests/test_recover_orphaned_turns_unittest.py \
  backend/tests/test_turn_orchestrator_cancel_unittest.py \
  backend/tests/test_workbench_app_gating_unittest.py \
  backend/tests/test_sql_bouncer_unittest.py \
  backend/tests/test_sherlock_azure_client.py
```

Then boot the backend — `manifest_validator` runs at startup and refuses to boot on manifest/semantic-model drift. Fix the manifest or the migration before anything else.
