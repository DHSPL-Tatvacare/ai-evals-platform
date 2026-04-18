# Investigation: sherlock-v2-tool-layer-drift

## What Was Investigated
Root-cause the patterns behind four Sherlock v2 failures observed in the
kaira-bot 15-turn smoke (`custom-user-work/sherlock_kaira_15turn.log`):
(1) `catalog_sample` rejecting `thread_evaluations`;
(2) `get_surface_records` rejecting `eval_runs`;
(3) `data_query` firing but no `chart` SSE event on explicit chart prompts
    (turns 12, 13);
(4) large swathes of "specialized" evidence tools (`get_app_stats`,
    `query_eval_runs`, `compare_runs`, `get_rule_compliance`, etc.) never
    chosen by the agent.

The goal was 30 000-ft: is this allow-list drift between
`tool_definitions.py`, `tool_handlers.py`, and the system prompt; is
chart binding broken; is tool-selection a prompting problem or something
else.

## Files and Entry Points
- `backend/app/services/report_builder/tool_definitions.py` — JSONSchema tool
  registry, `CAPABILITY_TOOLS`, `resolve_tools()`, `_DEPRECATED_DATA_EXPLORER_TOOLS`.
- `backend/app/services/report_builder/tool_handlers.py` — handler dispatch
  (`handle_catalog_sample`, `handle_get_surface_records`, `handle_data_query`).
- `backend/app/services/report_builder/chat_handler.py` — SSE wiring,
  `_build_chart_payload` (`chart` event emitter).
- `backend/app/services/report_builder/scratchpad_state.py` — stores
  `chart_options` across turns.
- `backend/app/services/chat_engine/catalog_tools.py` — `catalog_sample`,
  `build_catalog_allowlist`, `_CATALOG_MODEL_MAP`, `_validate_table_access`.
- `backend/app/services/chat_engine/data_surfaces.py` — `build_surface_catalog`,
  `get_surface_by_key` (reads `App.config.chat.dataSurfaces`).
- `backend/app/services/chat_engine/sql_agent.py` — `data_query`,
  `generate_sql`, `_build_chart_options`, `_validate_chart_spec_hint`,
  `MAX_QUERY_ATTEMPTS` (=3).
- `backend/app/services/chat_engine/prompts/base.py` — Sherlock system prompt
  (Layer 1).
- DB: `apps.config -> $.chat.dataSurfaces` for kaira-bot.
- Smoke log: `custom-user-work/sherlock_kaira_15turn.log`.
- Backend logs (live): `docker logs evals-backend`.

## Trace

### A. Tool registry: what the agent actually has
[tool_definitions.py:608-619](backend/app/services/report_builder/tool_definitions.py#L608-L619)

```python
CAPABILITY_TOOLS = {
    "catalog": CATALOG_TOOLS,        # 4 tools
    "discovery": DISCOVERY_TOOLS,    # 2 tools
    "evidence": EVIDENCE_TOOLS,      # 2 tools
    "report_builder": REPORT_BUILDER_TOOLS,  # 4 tools
    "analytics": ANALYTICS_TOOLS,    # 2 tools
    # "data_explorer": _DEPRECATED_DATA_EXPLORER_TOOLS,   # ← commented out
}
DEFAULT_CAPABILITIES = ["catalog", "discovery", "analytics", "evidence", "report_builder"]
```

`_DEPRECATED_DATA_EXPLORER_TOOLS` (tool_definitions.py:385-604) contains
`query_eval_runs`, `get_run_summary`, `compare_runs`, `query_threads`,
`get_app_stats`, `get_report_section`, `get_thread_detail`,
`get_rule_compliance`, `query_adversarial`, `get_cross_run_rule_compliance`
— **10 tools, all commented out of the registry** with the in-file
comment:

> "Superseded by the 'analyze' tool which uses semantic SQL generation.
>  Unplugged from the default capability set but kept in code."

**Fact:** The default-registered tool count is **14**, not 24.
The earlier exploration that said "24 tools" counted the deprecated list.
The smoke-test's "missing 11 tools" framing is wrong — 10 of those 11
cannot be called because they are not registered; only `catalog_inspect`
was truly unused (the agent chose `discover` instead in turn 1, reasonable).

### B. `catalog_sample` allow-list mismatch
[catalog_tools.py:31-36](backend/app/services/chat_engine/catalog_tools.py#L31-L36):

```python
_CATALOG_MODEL_MAP: dict[str, Any] = {
    'analytics_run_facts': AnalyticsRunFact,
    'analytics_eval_facts': AnalyticsEvalFact,
    'analytics_criterion_facts': AnalyticsCriterionFact,
    'eval_runs': EvalRun,
}
```

[catalog_tools.py:91-99](backend/app/services/chat_engine/catalog_tools.py#L91-L99) — `build_catalog_allowlist` returns the
intersection of semantic-model tables with this ORM map, + `eval_runs`.
The whole catalog_* family (inspect, relations, values, sample) is
hard-limited to these four tables because the map is keyed by ORM class.

[catalog_tools.py:514-519](backend/app/services/chat_engine/catalog_tools.py#L514-L519) — the error message the agent saw:

> "Unknown or disallowed table: thread_evaluations. Valid tables are:
>  analytics_criterion_facts, analytics_eval_facts, analytics_run_facts,
>  eval_runs"

Meanwhile [tool_definitions.py:346](backend/app/services/report_builder/tool_definitions.py#L346) — the `data_check` tool
description the agent *reads* says:

> `"table": "Canonical table name to check, such as eval_runs or thread_evaluations."`

The tool-description vocabulary advertises a table name the catalog
layer has never heard of. The agent was following instructions.

### C. `get_surface_records` naming namespace collision
`get_surface_records` reads the surface catalog from
`App.config.chat.dataSurfaces`. For kaira-bot (confirmed via
`SELECT config->'chat'->'dataSurfaces' FROM apps WHERE slug='kaira-bot'`):

```
["runs", "logs", "thread_evaluations", "adversarial_evaluations"]
```

The valid surface keys are `runs / logs / thread_evaluations /
adversarial_evaluations`. The catalog allow-list (B above) names an ORM
table `eval_runs`. These two namespaces share concepts but not strings.

[tool_handlers.py:459-465](backend/app/services/report_builder/tool_handlers.py#L459-L465) — when the agent called
`get_surface_records(surface_key='eval_runs')` (turns 10, 11, 14, 15 of the
smoke), the handler returns:

> `'Unknown surface: eval_runs'` + available_surfaces.

The system prompt ([prompts/base.py:36-39](backend/app/services/chat_engine/prompts/base.py#L36-L39)) describes
`get_surface_records` as retrieving "logs, thread artifacts, nested
evaluation payloads, and run records" — the phrase "run records" nudges
the agent toward `eval_runs` (a catalog table name) rather than `runs`
(the surface key). Nothing in the tool schema enforces "must come from
discover() output".

### D. Chart SSE event emission path
Flow: `data_query` → result payload with `chart_options` →
`_build_chart_payload` → SSE `chart` event.

[chat_handler.py:113-129](backend/app/services/report_builder/chat_handler.py#L113-L129):

```python
def _build_chart_payload(result):
    if not isinstance(result, dict) or result.get('status') != 'ok':
        return None
    ...
    suggested = chart_options.get('suggested')
    if not isinstance(suggested, dict):
        return None
    chart_type = ...; x_key = ...; y_keys = ...
    if not chart_type or not x_key or not y_keys:
        return None
```

**No chart event is emitted unless `data_query` returned
`status='ok'` AND `chart_options.suggested` has {type, x, y}.**

[sql_agent.py:954-1033](backend/app/services/chat_engine/sql_agent.py#L954-L1033) — `_build_chart_options` populates `suggested`
from one of two sources:
1. an LLM-provided `chart_spec_hint` (from `generate_sql`'s output fields
   `chart_type`, `x_key`, `y_keys`) that passes `_validate_chart_spec_hint`
   — both the hint's x_key and y_keys must literally match column names
   in the query output; and
2. a rule-based fallback that requires at least one output column tagged
   `role='measure'` in the column-metadata builder.

### E. What actually happened on turns 12 and 13 (backend logs)
Turn 12 ("Show me pass rate by evaluator for kaira-bot as a bar chart"):

- LLM-generated SQL (attempt 1):
  `SELECT er.evaluator_name AS evaluator_name, ROUND(AVG(rf.pass_rate), 2) AS pass_rate_percentage FROM analytics_run_facts rf JOIN eval_runs er ON rf.run_id = er.id ...`
  → `column er.evaluator_name does not exist` (hallucinated column).
- Attempt 2 SQL:
  `SELECT rf.run_name AS evaluator_name, ROUND(AVG(rf.pass_rate), 2) AS pass_rate_percentage FROM analytics_run_facts rf ...`
  → `function round(double precision, integer) does not exist`
  (missed the PostgreSQL numeric-cast rule).
- Attempt 3 (not shown in the excerpt but within `MAX_QUERY_ATTEMPTS=3`)
  either recovers or raises; the tool returned with 249 characters of
  content and no chart, so `chart_options.suggested` was not populated
  — either because `status != 'ok'` or the final column shape did not
  carry a `measure`-tagged column.

Turn 13 ("Show rule compliance across the last 3 runs as a chart"):

- Earlier turn 08 had already hit `column cf.rule does not exist` and
  `column er.run_name does not exist` on the same concept. The agent
  hallucinates column names (`cf.rule` vs the real `cf.criterion_label`;
  `er.run_name` vs. eval_runs having no such column).
- Turn 13 SQL uses `analytics_run_facts.run_id / created_at / pass_rate`
  with a row-number window — likely recovered, but the output column
  names (`pass_rate` / `compliance_rate`) are aggregate aliases whose
  `role` in `_column_metadata_from_select` depends on matching against
  the semantic model / pg `COMMENT ON COLUMN` text. Aggregate aliases
  have no pg_description row → no `role='measure'` → rule-based
  suggester returns `suggested=None`.
- Net effect: the tool "succeeded" but `chart_options.suggested` was
  empty, so `_build_chart_payload` returned None, so no `chart` SSE.

### F. Why turns 8, 9, 14 *did* emit charts
These SQLs selected base columns with semantic comments (e.g.
`analytics_run_facts.created_at` + `pass_rate` — both have `COMMENT ON
COLUMN` metadata in `startup_schema.py:281-295`). The metadata builder
tagged them `temporal` and `measure`, the rule-based suggester found a
valid `x=temporal, y=measure` pairing, and the chart event fired. The
agent's SQL shape, not intent, decides whether a chart appears.

## Findings

1. **(Confirmed) Tool-count misreporting from earlier exploration.** The
   agent is given 14 tools by default, not 24. 10 named tools
   (`query_eval_runs`, `get_run_summary`, `compare_runs`, `query_threads`,
   `get_app_stats`, `get_report_section`, `get_thread_detail`,
   `get_rule_compliance`, `query_adversarial`, `get_cross_run_rule_compliance`)
   live in a `_DEPRECATED_DATA_EXPLORER_TOOLS` list that is **commented
   out** of `CAPABILITY_TOOLS`. The 15-turn smoke therefore fired
   13/14 registered tools — good coverage, not bad.

2. **(Confirmed) `catalog_*` family is ORM-model-bound and cannot see
   non-analytics tables.** `_CATALOG_MODEL_MAP` locks the allow-list to
   four tables. Any prompt that names `thread_evaluations`,
   `adversarial_evaluations`, `threads`, `rules`, etc. will be rejected
   with "Unknown or disallowed table".

3. **(Confirmed) Vocabulary in tool descriptions leaks unsupported
   names.** `data_check`'s inputSchema description literally says
   `"such as eval_runs or thread_evaluations"`, yet the catalog layer
   rejects `thread_evaluations`. The agent obeyed the description; the
   implementation betrayed it.

4. **(Confirmed) Two disjoint namespaces for "runs".**
   - ORM/catalog namespace: `eval_runs` (a SQLAlchemy-mapped table).
   - Surface namespace (per-app config): `runs`, `logs`,
     `thread_evaluations`, `adversarial_evaluations`.
   `get_surface_records(surface_key=...)` requires the second namespace;
   `catalog_*` and `data_check` use the first. The system prompt uses
   both words ("runs", "run records", "eval_runs") without distinguishing
   them. The agent conflated them on 4 of 15 turns.

5. **(Confirmed) Chart emission depends on SQL output shape, not user
   intent.** Two gates must be passed before a `chart` SSE fires:
   (a) `data_query` returns `status='ok'` with data; (b) either the LLM's
   optional `chart_spec_hint` validates against the exact output column
   names, or at least one output column is tagged `role='measure'` via
   semantic-model/pg_description matching. Aggregate aliases
   (`pass_rate_percentage`, `compliance_rate`, etc.) produced by
   `generate_sql` have no `COMMENT ON COLUMN` entry and typically fall
   through both gates. An explicit user request for "a bar chart" does
   not force chart emission.

6. **(Confirmed) SQL generation is the silent primary source of pain.**
   Backend logs show repeated column hallucinations:
   `er.evaluator_name`, `cf.rule`, `er.run_name`, `cf.rule_compliance_rate`.
   The retry loop (`MAX_QUERY_ATTEMPTS=3`) absorbs these, so the
   user-facing result looks "done / degraded" while the tool burned
   3 × LLM calls + 3 × DB round-trips per turn. Turn 12 took 31 s. This
   masks a semantic-model-vs-actual-schema mismatch that is the real
   root cause of the "no chart" symptom in turns 12 / 13.

7. **(Suspected) Semantic-model / comment drift.** The LLM hallucinates
   `cf.rule` when the real column is `cf.criterion_label`
   (`startup_schema.py:290`). Either the LLM's schema context is
   inaccurate, or it is being ignored. A targeted check of what
   `schema_context` is actually passed into `generate_sql` for kaira-bot
   would confirm.

8. **(Suspected) Degraded status vs. error status.** Three of the 15
   turns returned `terminal_status='degraded'` with the tool warnings
   propagated in plain prose. This keeps the user happy (the agent
   *wrote* an answer) but hides integration bugs. Downstream telemetry
   that only alarms on `error` will miss all of these.

9. **(Pattern-level: 30 000 ft verdict)** This is not "bad coding". It
   is a **contract-drift problem across three adjacent surfaces** that
   were each built separately and never reconciled:

   | Surface            | Owns           | Source of truth                    |
   |--------------------|---------------|------------------------------------|
   | ORM catalog tools  | 4 tables      | `_CATALOG_MODEL_MAP` (code)        |
   | Data surfaces      | 4 surface keys| `apps.config.chat.dataSurfaces` (DB)|
   | Tool descriptions  | Prose list    | `tool_definitions.py` JSONSchema   |
   | System prompt      | Prose list    | `prompts/base.py`                  |
   | Semantic model     | Column roles  | `semantic_models/*.yaml` + pg COMMENT|

   Each of the five lists is maintained by hand. None validates against
   any other. The agent is asked to reconcile them at runtime from
   natural-language descriptions — it cannot, and the tool handlers
   reject it when it guesses wrong. The smoke failures are each an
   instance of the same underlying defect: **no single-source-of-truth
   contract, no build-time cross-check, no runtime schema negotiation**.

## Open Questions

- Is `schema_context` for `generate_sql` sourced from live DB
  introspection (pg_description) or from the static YAML under
  `backend/app/services/chat_engine/semantic_models/`? If YAML, who
  keeps it in sync with `startup_schema.py` and Alembic migrations?
- Did the tool-registry change in phases 2-6 (the Moriarty merge
  referenced in `git log`) intend to delete `_DEPRECATED_DATA_EXPLORER_TOOLS`
  and forget, or keep them as a contingency? Dead code in a 3 000-line
  registry is itself a contract-drift risk.
- Should chart emission be triggered by entity_recognition detecting a
  "show as chart" user intent independently of SQL output shape? The
  current design silently swallows the intent.
- Is there a reason `catalog_*` is ORM-bound instead of reading
  `information_schema` directly? The project memory
  `project_sherlock_v2_architecture.md` claims catalog_inspect queries
  `information_schema + pg_catalog.pg_description`, but the code clearly
  goes through a SQLAlchemy ORM model — that contradicts the design doc.

## Recommended Next Step

Run a short audit of the five lists in finding #9 side-by-side (export
each, diff them for name mismatches), then bring them under a single
source-of-truth contract — either live introspection or a checked-in
manifest validated at startup. The individual bugs (catalog allow-list,
surface-key confusion, chart-on-intent) are symptoms of that one
structural gap; fixing each symptom in isolation will let them re-drift.
