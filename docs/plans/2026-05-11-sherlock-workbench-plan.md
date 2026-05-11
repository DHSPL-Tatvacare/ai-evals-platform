# Sherlock — The Workbench Era (Implementation Plan)

**Date:** 2026-05-11
**Status:** Proposed, awaiting review
**Design spec:** [`2026-05-11-sherlock-workbench-design.md`](./2026-05-11-sherlock-workbench-design.md)
**Supersedes:** the earlier `2026-05-11-sherlock-data-specialist-single-pipe.md` (now a stub).

---

This plan is organized around the four work items the user locked:

1. **Sherlock hardening — the new flow.** Bouncer + granularity graph + retry/refuse + honest pagination.
2. **Supervisor + Specialists philosophy.** Add `query_synthesis_specialist`. Rewrite supervisor prompt to be a pure router. Keep `data_specialist` and `authoring_specialist` wired via `as_tool`.
3. **Manifest rewrite.** Inside-sales first, then voice-rx, then kaira-bot. Cortex Analyst shape. JSONB-derived columns.
4. **Kill custom Python.** Delete regex classifier, dead validators, legacy duplicates. Engineering only at the right layers.

Phases are sequenced so each one delivers a working, testable change with concrete validation. **Each phase carries a per-app toggle (`app.config.chat.workbench_enabled`) so we roll out one app at a time.** The toggle itself is deleted at the end of Phase 7.

---

## Phase 1 — Inside-Sales Catalog Rewrite (Work Item 3)

**Goal.** Rewrite `semantic_models/inside-sales.yaml` to Cortex Analyst shape. Expose the curated set of 6 fact/aggregate tables. Add ~30 derived logical columns from `fact_evaluation.result_detail` and 6 from `fact_lead_activity.attributes`. Boot validator enforces required fields and cross-checks the workbench catalog against the existing manifest surface so the two YAML families cannot drift.

**Files added.** None.

**Files modified.**
- `backend/app/services/chat_engine/semantic_models/inside-sales.yaml` — full rewrite.
- `backend/app/services/chat_engine/manifests/inside-sales.yaml` — strip the 5 tables no Sherlock query touches (`evaluators`, `evaluation_runs`, `crm_call_record`, `crm_lead_record`, `fact_lead_signal`). Keep only `agg_evaluation_run`, `fact_evaluation`, `dim_lead`, `fact_lead_stage_transition`, `fact_lead_activity`, plus the 3 forensic data_surfaces (`runs`, `logs`, `thread_evaluations`). This file remains the physical/taxonomy/data-surface compatibility contract during rollout; it is not allowed to contradict the workbench semantic model.
- `backend/app/services/chat_engine/manifest_validator.py` — extend with: `physical_primary_key.columns` and `analytical_grain.columns` required on every fact/aggregate table; `relationships[]` entries must reference declared tables; `dimensions[]` with `is_enum: true` must have non-empty `sample_values`; `verified_queries[]` must have ≥ 3 entries per app; semantic-model tables/columns must be present in the app manifest or explicitly marked derived.
- `backend/app/services/chat_engine/manifest.py` — add Pydantic models/loaders for the workbench semantic catalog (`WorkbenchCatalog`, `WorkbenchTable`, `LogicalColumn`, `Relationship`, `VerifiedQuery`). Do not overload the legacy `CatalogTable.grain`; keep physical keys, tenant-scoped unique keys, and analytical grains as separate concepts.

**Files deleted.** None in this phase.

**Catalog content for inside-sales** (per the manifest audit and the rubric-key reconnaissance):

```yaml
name: inside_sales_model
description: Sherlock semantic model for inside-sales call rubric + lead pipeline analytics

custom_instructions: |
  Quality scoring for inside-sales calls uses the 'GoodFlip Sales Call QA' rubric on a 0–45.7 scale.
  result_status is always NULL for this app — use result_score and rubric-derived columns for quality analysis.
  fact_evaluation_criterion has no rows for this app (call_rubric does not emit criterion-level data).
  Use dim_lead for lead identity, fact_lead_activity for calls/activities, fact_lead_stage_transition for stage history.

module_custom_instructions:
  sql_generation: |
    Aggregate eval rubric scores at the (run_id, agent) grain.
    Lead-pipeline questions: always join through dim_lead.lead_id.
    Never join fact_evaluation to fact_lead_activity directly — they live on different grains.

tables:
  - name: agg_evaluation_run
    base_table: { database: ai_evals_platform, schema: analytics, table: agg_evaluation_run }
    physical_primary_key: { columns: [id] }
    analytical_grain: { columns: [run_id] }
    description: One row per eval run (call_rubric or full_evaluation), aggregated.
    dimensions: [run_name, eval_type, status]
    time_dimensions: [created_at, completed_at]
    facts: [thread_count, pass_count, fail_count, error_count, avg_score, duration_ms]
    metrics:
      - name: avg_call_score
        expr: ROUND(AVG(avg_score)::numeric, 2)
        description: Average rubric score per run (0–45.7)

  - name: fact_evaluation
    base_table: { database: ai_evals_platform, schema: analytics, table: fact_evaluation }
    physical_primary_key: { columns: [id] }
    analytical_grain: { columns: [run_id, item_id, evaluator_id] }
    description: One row per (run, call_recording, evaluator) — the evaluator-graded result.

    dimensions:
      # Scalar columns
      - name: agent
        expr: agent
        data_type: nominal
        physical_type: text
        description: TatvaCare inside-sales rep name (human)
      - name: direction
        expr: direction
        data_type: nominal
        physical_type: text
        is_enum: true
        sample_values: [inbound, outbound]
      - name: evaluator_id
        expr: evaluator_id
        data_type: nominal
        physical_type: uuid
      - name: result_verdict
        expr: result_verdict
        data_type: nominal
        physical_type: text

      # JSONB-derived: result_detail rubric scores (call_rubric eval_type)
      - name: call_opening_score
        expr: "(result_detail->>'call_opening')::numeric"
        data_type: quantitative
        physical_type: numeric
        description: Call-opening rubric score (0–10)
      - name: brand_positioning_score
        expr: "(result_detail->>'brand_positioning')::numeric"
        data_type: quantitative
        physical_type: numeric
      # ... continue for: credibility_safety, intent_decision_mapping,
      #     metabolic_score_explanation, metabolism_explanation, probing_quality,
      #     program_mapping, transition_probing, closing_impression, overall_score

      # JSONB-derived: yes/no outcome flags
      - name: callback_occurred
        expr: "result_detail->>'callback_occurred'"
        data_type: nominal
        physical_type: text
        is_enum: true
        sample_values: [Yes, No]
      # ... continue for: crosssell_accepted, crosssell_attempted, disagreement_present,
      #     escalation_present, meeting_occurred, purchase_occurred

      # JSONB-derived: compliance booleans
      - name: compliance_no_guarantees
        expr: "(result_detail->>'compliance_no_guarantees')::boolean"
        data_type: boolean
        physical_type: boolean
      # ... continue for: compliance_no_misinformation, compliance_no_stop_medicines

      # JSONB-derived: full_evaluation rubric (different eval_type)
      - name: communication_skills_score
        expr: "(result_detail->>'communication_skills')::numeric"
        data_type: quantitative
        physical_type: numeric
      # ... continue for: product_knowledge, need_analysis, objection_handling,
      #     urgency_creation, actions_offer, call_closure

      # JSONB-derived: rating categories
      - name: call_opening_rating
        expr: "result_detail->>'call_opening_rating'"
        data_type: nominal
        physical_type: text
      # ... continue for the 7 *_rating siblings

      # JSONB-derived: ZTP (full_evaluation)
      - name: ztp_violation
        expr: "(result_detail->>'ztp_violation')::boolean"
        data_type: boolean
        physical_type: boolean

    time_dimensions:
      - name: created_at
        expr: created_at
        data_type: temporal
        physical_type: timestamptz

    facts:
      - name: result_score
        expr: result_score
        data_type: quantitative
        physical_type: double precision
      - name: duration_seconds
        expr: duration_seconds
        data_type: quantitative
        physical_type: double precision

    metrics:
      - name: avg_call_score
        expr: ROUND(AVG(result_score)::numeric, 2)
      - name: avg_call_opening
        expr: ROUND(AVG((result_detail->>'call_opening')::numeric), 2)
      - name: ztp_violation_rate
        expr: "AVG(CASE WHEN (result_detail->>'ztp_violation')::boolean THEN 1.0 ELSE 0.0 END)"

  - name: dim_lead
    base_table: { database: ai_evals_platform, schema: analytics, table: dim_lead }
    physical_primary_key: { columns: [id] }
    analytical_grain: { columns: [lead_id] }
    description: SCD-1 lead dimension; one row per lead with latest stage.
    dimensions: [lead_id, source, latest_stage_observed]
    time_dimensions: [lsq_created_on, first_seen_at, latest_stage_observed_at]

  - name: fact_lead_stage_transition
    base_table: { database: ai_evals_platform, schema: analytics, table: fact_lead_stage_transition }
    physical_primary_key: { columns: [id] }
    analytical_grain: { columns: [id] }
    description: Append-only lead stage transitions.
    dimensions: [lead_id, from_stage, to_stage]
    time_dimensions: [detected_at, transition_at]

  - name: fact_lead_activity
    base_table: { database: ai_evals_platform, schema: analytics, table: fact_lead_activity }
    physical_primary_key: { columns: [id] }
    tenant_scoped_unique_key: { columns: [tenant_id, app_id, source_activity_id] }
    analytical_grain: { columns: [source_activity_id] }
    description: Lead activities (calls, events). 100% calls today; activity_type='call'.
    dimensions:
      - name: lead_id
        expr: lead_id
      - name: activity_type
        expr: activity_type
        is_enum: true
        sample_values: [call]
      - name: agent_email
        expr: "attributes->>'agent_email'"
        data_type: nominal
        physical_type: text
      - name: agent_name
        expr: "attributes->>'agent_name'"
        data_type: nominal
        physical_type: text
      - name: status
        expr: "attributes->>'status'"
        data_type: nominal
        physical_type: text
      - name: phone_number
        expr: "attributes->>'phone_number'"
        data_type: nominal
        physical_type: text
    time_dimensions: [occurred_at]
    facts:
      - name: duration_seconds
        expr: "(attributes->>'duration_seconds')::numeric"
        data_type: quantitative
        physical_type: numeric

relationships:
  - name: fact_eval_to_agg_run
    left_table: fact_evaluation
    right_table: agg_evaluation_run
    relationship_columns: [{ left_column: run_id, right_column: run_id }]
    join_type: inner
    relationship_type: many_to_one

  - name: stage_transition_to_lead
    left_table: fact_lead_stage_transition
    right_table: dim_lead
    relationship_columns: [{ left_column: lead_id, right_column: lead_id }]
    join_type: inner
    relationship_type: many_to_one

  - name: lead_activity_to_lead
    left_table: fact_lead_activity
    right_table: dim_lead
    relationship_columns: [{ left_column: lead_id, right_column: lead_id }]
    join_type: inner
    relationship_type: many_to_one

verified_queries:
  - name: avg_call_score_by_agent_this_week
    question: "What is the average call quality for each agent this week?"
    sql: |
      SELECT agent, ROUND(AVG(result_score)::numeric, 2) AS avg_score, COUNT(*) AS calls
      FROM analytics.fact_evaluation
      WHERE tenant_id = :tenant_id AND app_id = :app_id
        AND created_at >= date_trunc('week', now())
      GROUP BY agent ORDER BY avg_score DESC LIMIT 50;

  - name: ztp_violations_last_30d
    question: "Which calls had ZTP violations in the last 30 days?"
    sql: |
      SELECT item_id, agent, created_at, result_detail->>'ztp_evidence' AS evidence
      FROM analytics.fact_evaluation
      WHERE tenant_id = :tenant_id AND app_id = :app_id
        AND (result_detail->>'ztp_violation')::boolean = true
        AND created_at >= now() - interval '30 days'
      ORDER BY created_at DESC LIMIT 100;

  - name: leads_stuck_over_7_days
    question: "Which leads have not moved stage in over 7 days?"
    sql: |
      SELECT lead_id, latest_stage_observed, latest_stage_observed_at
      FROM analytics.dim_lead
      WHERE tenant_id = :tenant_id AND app_id = :app_id
        AND latest_stage_observed_at < now() - interval '7 days'
      ORDER BY latest_stage_observed_at ASC LIMIT 100;
```

(The full ~30 dimensions + 10 metrics will be authored in the actual YAML — the above is a representative skeleton.)

**Validation criteria.**
- [ ] `python -m app.services.chat_engine.manifest_validator --app inside-sales --strict` exits 0.
- [ ] Booting the backend with the new YAML succeeds; removing `physical_primary_key` or `analytical_grain` from any fact/aggregate table causes boot to fail with a clear error.
- [ ] Every `dimensions[]` entry with `is_enum: true` carries non-empty `sample_values` (validator-enforced).
- [ ] Every join in `relationships[]` references a declared table.
- [ ] `verified_queries[]` has at least 3 entries.
- [ ] The semantic model and app manifest agree on every physical table/column; derived columns declare an expression and physical source.
- [ ] No table in `catalog_tables` for inside-sales whose name appears 0 times in the last 90 days of `analytics.log_sherlock_tool_call.generated_sql` (sanity-check the curation).
- [ ] Spot-check: 5 of the 30 JSONB-derived columns return the expected scalar when SELECTed against prod data (read-only verification only).
- [ ] Run `EXPLAIN` for the top 3 verified inside-sales queries. Add expression indexes or materialized facts only if the plans show JSONB extracts are the bottleneck.

---

## Phase 2 — Granularity Graph + Bouncer (Work Item 1)

**Goal.** Build the deterministic safety surface. New module: `sql_bouncer.py` (one module, two functions: `check_before(sql, declared_grain, expected_row_bound, catalog) -> Verdict`, `check_after(rows, ...) -> Verdict`). New helper: `granularity_graph.py` (built at boot from catalog). The bouncer uses a real PostgreSQL-capable SQL AST parser; regex validation is explicitly out of scope for this layer.

**Files added.**
- `backend/app/services/chat_engine/granularity_graph.py` (~250 lines)
- `backend/app/services/chat_engine/sql_bouncer.py` (~500 lines + tests)
- `backend/tests/test_sql_bouncer.py`
- `backend/tests/test_granularity_graph.py`

**Files modified.**
- `backend/app/services/sherlock_v3/data_specialist.py:53-110` — `_SUBMIT_SQL_SCHEMA` adds required `declared_grain: list[str]` and `expected_row_bound: enum` fields.
- `backend/app/services/sherlock_v3/data_specialist.py:_submit_sql_handler` — body wraps `sql_bouncer.check_before` → `prepare_query` → `execute_query` → `sql_bouncer.check_after`.
- `backend/app/services/chat_engine/sql_agent.py` — `execute_query` switches from silent `LIMIT 200` to server-owned `LIMIT (cap+1)` injected by the bouncer; returns `rows`, `more_rows_exist`, `displayed_row_count`, and `limit_applied`.
- `pyproject.toml` / lockfile — add the chosen SQL AST parser dependency (prefer a PostgreSQL-capable library such as `sqlglot`; document the choice in `sql_bouncer.py`).

**Files deleted.** None yet (deletions happen in Phase 6).

**Bouncer rules** (lifted from the design spec §4 verbatim):
- Pre-execution (R1–R8b): allowed tables, allowed columns, declared-joins-only, graph-aware aggregate placement, GROUP BY completeness, tenant/app filters on every table alias in a join, honest LIMIT, fan trap, chasm trap.
- Post-execution (R9–R12): grain-of-result match, no duplicate rows, row-limit truth, not-all-null.

**Validation criteria.**
- [ ] Synthetic test for each rule: one positive (clean SQL passes), one negative (violating SQL is rejected with the right diagnostic). 11 rules × 2 cases = 22 unit tests minimum.
- [ ] AST parser tests cover aliases, CTEs, nested subqueries, quoted identifiers, casts, schema-qualified tables, and comments/stacked statements.
- [ ] Multi-table tests prove every joined table alias is tenant/app scoped; filtering only the primary table is rejected.
- [ ] **R3 fires** on the kaira-bot historical hallucinated join `JOIN eval_runs ON rf.run_id = e.id` (synthetic test fixture from the audit).
- [ ] **R8b (chasm trap) fires** on tool log `cf18c0af-…`'s SQL pattern — the multi-fact join with `COUNT(*)` aggregating both sides.
- [ ] **R9 fires** on tool log `6e78c363-…`'s composite-grain duplicate fixture.
- [ ] **R7+R11 fire** on turn `4ce801f1-…`'s unbounded query — bouncer rewrites to `LIMIT 201`, result has 201 rows, trimmed to 200, `more_rows_exist=true` propagates.
- [ ] All bouncer rules have zero LLM dependencies (no Anthropic/OpenAI imports in the module).
- [ ] `submit_sql` returns `more_rows_exist`, `displayed_row_count`, `limit_applied`, and a structured `bouncer` object (`rule_id`, `diagnostic`, `declared_grain`, `expected_row_bound`) for telemetry.
- [ ] `pytest backend/tests/test_sql_bouncer.py backend/tests/test_granularity_graph.py` is green.

---

## Phase 3 — Query Synthesis Specialist (Work Item 2)

**Goal.** Add the third specialist. Owns rewrite + classify + decompose. Exposes a strict Pydantic structured output. Wired into the supervisor via `as_tool`. The supervisor's prompt is rewritten to always call query synthesis first. The synthesis specialist only sees targets that are available in the supervisor toolbelt for this turn.

**Files added.**
- `backend/app/services/sherlock_v3/query_synthesis_specialist.py` (~200 lines).
- `backend/app/services/sherlock_v3/contracts.py` — new Pydantic model `SynthesisBrief` with `rewritten_question: str`, `classification: Literal[answerable, ambiguous, non_data, non_sql_data]`, `reason: str`, `suggested_followups: list[str]`, `available_targets: list[Literal[data_specialist, authoring_specialist]]`, `decomposition: list[SubQuestion]`.

**Files modified.**
- `backend/app/services/sherlock_v3/supervisor.py` — prompt rewrite. New prompt: "(1) Always call `query_synthesis_specialist` first. (2) If classification is not `answerable`, refuse with `suggested_followups`. (3) For each `SubQuestion`, call the tagged target specialist with the sub-question and any prior sub-question results as context. (4) Compose the final answer."
- `backend/app/services/sherlock_v3/supervisor.py` — toolbelt gains `query_synthesis_specialist.as_tool()`. The supervisor computes `available_targets` from the actual toolbelt after permission/context gating, then passes it into the synthesis tool call.
- `backend/app/services/sherlock_v3/data_specialist_prompt.py` — rewritten to be a clean catalog + verified-examples workbench prompt. SQL-hygiene prose deleted (the bouncer enforces those rules now).

**Files deleted.** None yet.

**Validation criteria.**
- [ ] `query_synthesis_specialist` returns a `SynthesisBrief` for 20 sample historical inside-sales questions. Manual audit: each rewrite is self-contained (no pronouns), each classification is correct, each decomposition matches the expected fan-out.
- [ ] Sample including 5 ambiguous questions ("tell me about my data"). Each gets `classification: ambiguous` with non-empty `suggested_followups`.
- [ ] Sample including 3 multi-part questions ("show me X and draft Y"). Each gets a `decomposition` with two entries, correctly tagged with `data_specialist` and `authoring_specialist`.
- [ ] Same multi-part sample without builder edit context or `orchestration:manage` permission does not emit `authoring_specialist`; it returns a data-only decomposition plus a follow-up/refusal for unavailable authoring.
- [ ] Supervisor playthrough: easy narrative from the design spec returns a correct chart with `more_rows_exist` flag honored.
- [ ] Supervisor playthrough: complex narrative from the design spec returns both the table and the email draft.
- [ ] No Python orchestration in `turn_orchestrator.py` outside of the single `Runner.run_streamed(supervisor_agent, ...)` call. (`grep -nE "Runner.run" backend/app/services/sherlock_v3/turn_orchestrator.py` shows one match.)

---

## Phase 4 — Kill Custom Python (Work Item 4)

**Goal.** Delete the patch layers that exist only because the workbench wasn't built. Engineering only at the right layers. Do not break non-Sherlock callers while deleting Sherlock legacy code.

**Files deleted.**
- `backend/app/services/sherlock_v3/intent_classifier.py` (143 lines, regex).
- `backend/app/services/sherlock_v3/manifest_projection.py` (236 lines, intent-keyed table filtering).
- `backend/app/services/chat_engine/result_verifier.py` (81 lines, dead code).

**Files modified.**
- `backend/app/services/chat_engine/sql_agent.py` — remove Sherlock's regex-only `validate_sql_columns_against_manifest`, `SQL_GENERATION_RESPONSE_SCHEMA`, and `SQL_AGENT_PROMPT`. Replace `validate_sql` with either the new shared AST read-only guard or a compatibility wrapper for remaining non-Sherlock callers such as `analytics/chart_executor.py`; do not delete the symbol until those callers have migrated. Keep only query preparation/execution helpers plus shared guard wrappers that still have live imports.
- `backend/app/services/sherlock_v3/runtime.py:351-439` — remove the intent-classifier call and the `project_for_intent` call. Pass the curated catalog whole as part of grounding context.
- `backend/app/services/sherlock_v3/data_specialist.py` — strip helpers that existed only to compensate for the regex validator. Slimmer.
- `backend/app/services/sherlock_v3/data_specialist_prompt.py` — remove the SQL-hygiene prose rules; replaced by the bouncer + catalog (changes already in Phase 3).

**Files added.** None.

**Validation criteria.**
- [ ] `grep -rnE "intent_classifier|manifest_projection|result_verifier|SQL_GENERATION_RESPONSE_SCHEMA|SQL_AGENT_PROMPT" backend/` returns zero matches.
- [ ] `rg "validate_sql" backend/app` shows only the shared AST guard/compatibility wrapper and intentional non-Sherlock callers, or zero matches if all callers migrated.
- [ ] All tests in `backend/tests/` still green (remove tests pinned to the deleted regex modules).
- [ ] Backend boots clean; lifespan logs show the manifest validator passing for all three apps.
- [ ] Net code change deletes the legacy Sherlock patch layers. Do not use line-count targets as acceptance criteria; acceptance is based on no legacy call sites, passing tests, and the replay set.

---

## Phase 5 — Inside-Sales Cutover + Soak

**Goal.** Flip `app.config.chat.workbench_enabled=true` for inside-sales. Soak for 1 week. Audit bouncer-fire rate, refusal rate, user-reported wrong answers, and truncation honesty.

**Files modified.**
- `backend/app/services/seed_defaults.py` — set inside-sales `chat.workbench_enabled=true`.
- `backend/app/services/sherlock_v3/runtime.py` — branch on the flag (legacy path stays alive for voice-rx and kaira-bot).
- `src/features/chat-widget/ChatMessages.tsx` / artifact-card components as needed — render `cannot_answer_safely` and bouncer diagnostics as an explicit safe refusal, not as a generic error or empty chart.
- `backend/app/schemas/sherlock.py` / `src/features/sherlock/queries/toolCalls.ts` as needed — expose bouncer telemetry from `analytics.log_sherlock_tool_call.arguments.bouncer` on the detail/logs surfaces.

**Validation criteria.**
- [ ] All three historical failure cases (turn `4ce801f1-…`, tool logs `6e78c363-…`, `cf18c0af-…`) replayed against the new pipeline. Each one either succeeds with correct chart + honest cardinality OR refuses with `cannot_answer_safely` and the right diagnostic. None silently shows a wrong chart.
- [ ] 7-day soak metric: bouncer-invalid rate < 15% of submit_sql calls; `cannot_answer_safely` rate < 5% of supervisor turns; zero confirmed user-reported wrong-chart incidents.
- [ ] Manual audit of 20 random Sherlock turns for inside-sales — all chart-card narratives are honest about cardinality and grain.
- [ ] Logs/tool-call detail show `rule_id`, `diagnostic`, `declared_grain`, `expected_row_bound`, `more_rows_exist`, `displayed_row_count`, and `limit_applied` for every `submit_sql` call.
- [ ] The chat widget renders a `cannot_answer_safely` refusal with the diagnostic text and no misleading chart artifact.

---

## Phase 6 — Voice-Rx + Kaira-Bot Catalog Rewrite (Work Item 3 continued)

**Goal.** Same Cortex-shape rewrite for the other two apps. Same curation rule: facts + aggregates only.

**Files modified.**
- `backend/app/services/chat_engine/semantic_models/voice-rx.yaml` — full rewrite.
- `backend/app/services/chat_engine/semantic_models/kaira-bot.yaml` — full rewrite. Drop `evaluators` table. Promote `evaluation_runs` columns the LLM has been pulling blind (`user_email`, `user_name`, `batch_metadata`) into `agg_evaluation_run` as logical columns, then drop `evaluation_runs` from exposure.
- `backend/app/services/chat_engine/manifests/voice-rx.yaml` + `kaira-bot.yaml` — strip dead tables.

**Validation criteria.**
- [ ] Manifest validator passes for both apps with `--strict`.
- [ ] Cortex-shape: every fact table declares `physical_primary_key` and `analytical_grain`; every join has `relationship_type`; every enum dimension has `sample_values`.
- [ ] kaira-bot's audit-found hallucinated join (`JOIN eval_runs ON rf.run_id = e.id`) is now structurally impossible — the granularity graph has no edge for it, the bouncer rejects.
- [ ] Each app has ≥ 3 `verified_queries[]` entries covering common questions.

---

## Phase 7 — Full Rollout + Toggle Removal

**Goal.** Flip workbench_enabled=true for voice-rx and kaira-bot. Remove the toggle. Delete the legacy code path.

**Files modified.**
- `backend/app/services/seed_defaults.py` — set workbench_enabled=true for all apps.
- `backend/app/services/sherlock_v3/runtime.py` — delete the `if workbench_enabled` branch; new pipeline is the only pipeline.

**Files deleted.** Any remaining "legacy specialist path" helpers.

**Validation criteria.**
- [ ] All three apps run the new pipeline.
- [ ] Two-week soak metric: same thresholds as Phase 5, across all apps.
- [ ] `grep -nE "workbench_enabled" backend/` returns zero matches.
- [ ] One Postgres VIEW `analytics.v_job_health` shipped (separate from this plan; tracked in the job-visibility design note). One `/api/jobs/health` route. One `/logs` tab. Operators can see job health without SQL.

---

## Risk register

- **Catalog drift.** Solution: manifest validator runs in CI on every PR. Cortex-shape conformance is enforced at boot, and the semantic model is cross-checked against the app manifest during the staged rollout.
- **Bouncer over-rejection.** Solution: each rule has a structured diagnostic; user-visible refusal copy makes false-positives easy to spot. Refusal soak metric in Phase 5/7 catches this.
- **Query synthesis hallucinations.** Solution: `SynthesisBrief` is strict Pydantic. Specialist call targets are an enum (`data_specialist | authoring_specialist`) constrained by the toolbelt available in that turn. The supervisor refuses if the brief is malformed or targets an unavailable specialist.
- **JSONB extract performance.** Solution: audit query plans for the top-3 verified queries during Phase 1. Add expression indexes or materialized facts only when `EXPLAIN` shows JSONB extraction is the bottleneck.
- **Multi-turn context loss.** Solution: existing `previous_response_id` chain on `sherlock_agent_sessions` is unchanged. Query synthesis sees the conversation history (passed as input to the agent loop).

## Decision log

All decisions are listed in §9 of the design spec. The plan does not re-decide; it executes. Any new decision discovered during implementation gets added to §9 of the design as an amendment, with date and rationale.

## Out of scope (for now)

- Vector search over schema tables.
- Token-budget trimming.
- Multi-turn dataset re-evaluation harness.
- Full redesign of the refusal UX. The minimal `cannot_answer_safely` rendering required for cutover is in Phase 5.
- Per-tenant catalog overrides — assume one catalog per app at the system tenant.

End of plan. Ready for review.
