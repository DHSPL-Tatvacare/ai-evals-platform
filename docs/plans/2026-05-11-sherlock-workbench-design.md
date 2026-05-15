# Sherlock — The Workbench Era (Design Spec)

**Date:** 2026-05-11
**Status:** Proposed, awaiting review
**Companion plan:** [`2026-05-11-sherlock-workbench-plan.md`](./2026-05-11-sherlock-workbench-plan.md)
**Investigation that drove this:** [`docs/investigations/sherlock-data-specialist-grain-cardinality.md`](../investigations/sherlock-data-specialist-grain-cardinality.md)

---

## 1. The story so far

Sherlock was meant to be a constrained analytics agent. Today it is a regex-stitched pipeline that the LLM can talk past in five different ways. The investigation linked above confirmed three live failure modes in prod-like local data — silent 200-row cardinality lies, composite-grain duplicate rows reaching the chart, and JOIN fan-out without DISTINCT. None of them are surfaced to the user.

Every guard we have is a band-aid. The regex `validate_sql` rejects DDL and not much else. `validate_sql_columns_against_manifest` is regex column extraction, defeated by the simplest CTE. `result_verifier.py` is fully written and has zero callers. The chartability gate inspects column shape but cannot detect that rows are duplicates. The intent classifier is regex pattern-matching trying to route `aggregate` vs `fact_grain` questions to different table sets — when it misclassifies, it hides the right table from the LLM and the LLM invents joins. And the silent `LIMIT 200` caps every result without telling anyone, so when the population is 472, the agent confidently says "200 items."

The manifest is half-built. Inside-sales has 11 declared tables; 6 have zero Sherlock traffic in 90 days. Three are empty in prod. Meanwhile, the rich rubric data — `fact_evaluation.result_detail` — is a JSONB column with 48 named fields per call, and not a single one is exposed to the LLM. The questions inside-sales analysts actually want to ask ("average call_opening score by agent") are mechanically unanswerable.

Each fix we tried over the last six months added another layer that the LLM has to navigate. The user's verdict was correct: nobody uses Sherlock today because it is shit. The fix is not another layer. It is a workbench.

## 2. The North Star

One supervisor LLM that runs the entire turn lifecycle. Three specialists, all wired to the supervisor as `as_tool`. A catalog the LLM can see in full because we curate it down to what matters. A deterministic bouncer that lives inside the SQL specialist's tool, not outside. One retry path. One refusal path. The custom Python that's been compensating for these missing pieces gets deleted.

The supervisor is the smart model. We empower it to do context engineering by giving it a query-synthesis helper specialist that owns rewriting, classifying, and decomposing the user's question. The supervisor then dispatches the resulting brief to the data or authoring specialist that does the actual work. The supervisor truly supervises — it doesn't sit outside a Python pipeline that pre-processes things behind its back.

LLMs are smart. They can process 10–20K tokens and emit complex structured output. Snowflake's Cortex Analyst publishes a multi-stage agent pipeline with exactly this shape and ships it in production. We are not inventing. We are catching up.

## 3. The TO-BE topology

```
                  ┌─ query_synthesis_specialist  (as_tool)
                  │     context engineering: rewrite + classify + decompose
                  │     output: structured brief with sub-questions tagged by target
                  │
SUPERVISOR ───────┼─ data_specialist             (as_tool)
                  │     writes SQL against curated catalog
                  │     submit_sql tool body wraps the bouncer
                  │
                  └─ authoring_specialist        (as_tool)
                        builds workflows / configs / drafts
                        unchanged from today
```

One Agent at the top (supervisor). Three Agents one level down, each exposed via `as_tool`. The whole turn is one `Runner.run_streamed` call on the supervisor. The Agents SDK orchestrates everything inside it.

The supervisor's playbook (in its prompt):
1. Always call `query_synthesis_specialist` first. Get back the structured brief.
2. If the brief says not answerable, refuse with the brief's suggested follow-ups. End turn.
3. For each sub-question in the brief, call the target specialist (`data_specialist` or `authoring_specialist`) with the sub-question and any prior-sub-question results as context.
4. Compose the final answer for the user.

That is it. No pre-Python, no intent classifier, no parallel Runner calls outside the supervisor.

## 4. The Workbench — what the supervisor and its specialists actually see

The workbench is the set of artifacts the supervisor and its specialists can reach for to do their job correctly. Five concrete pieces:

**1. The curated catalog** (`semantic_models/<app>.yaml`, Cortex Analyst shape).
This is one contract, not two parallel sources of truth. The implementation may keep compatibility fields in `manifests/<app>.yaml` while the rollout is staged, but boot validation must cross-check the two surfaces and fail on drift. Each fact and aggregate table declares both its physical key and analytical grain, joins with cardinality, dimensions with allowed-value enums, time dimensions with date types, facts and measures with their canonical aggregation expressions, named filters, and verified queries. Boot fails on any fact/aggregate table missing analytical grain or a physical key. Only `analytics_fact` and `analytics_aggregate` tables are exposed — never transactional, identity, or empty tables. JSONB rich columns (the load-bearing case: `fact_evaluation.result_detail` with 48 rubric keys for inside-sales) are exposed as derived logical columns, each with a Postgres extract expression. The LLM never sees `->>` syntax.

**2. Verified queries**.
Golden question→SQL pairs co-located with each app's catalog and seeded into the existing verified-query store. The data specialist sees the top 3–5 most similar verified queries in its prompt every turn. Phase 1 keeps the current deterministic lexical retrieval unless a separate embedding/index migration is explicitly added; the architectural requirement is retrieval of verified examples, not vector search as a hidden dependency. This is Cortex's Verified Query Repository pattern, ported.

**3. The granularity graph**.
Built once at boot from the catalog's `relationships[]` and analytical-grain declarations. Directed graph. Nodes are unique analytical granularities (1:1-related tables collapse). Edges are many-to-one joins. This is the data structure the bouncer walks. Algorithm lifted from the Cortex Analyst joins post, adapted for Postgres and tenant-scoped facts.

**4. The bouncer**.
One Python module. Two entry points: `check_before(sql, ...)` and `check_after(rows, ...)`. Both return either `ok` or `invalid` with a structured diagnostic. Lives inside the body of the `submit_sql` `FunctionTool`. Eleven rules, all deterministic, no LLM. Pre-execution rules walk the granularity graph (joins declared? aggregate at lowest grain? fan trap? chasm trap?) and a real SQL AST (allowed tables, alias resolution, allowed columns, GROUP BY completeness, tenant/app filters on every joined table, honest LIMIT). Post-execution rules scan rows (grain matches declaration? duplicate rows? row-limit truth? all-null columns?). Regex checks are not acceptable for this layer.

**5. Honest pagination**.
The `submit_sql` tool's schema gains two required fields: `declared_grain: [column names]` and `expected_row_bound: enum(single|small|medium|large|unbounded)`. `expected_row_bound` is a hint from the LLM, not an authority. The server chooses the cap, rewrites the SQL to `LIMIT N+1`, executes, and if N+1 rows come back, trims and sets `more_rows_exist=true`, `displayed_row_count`, and `limit_applied`. The chart card surfaces this. The agent's narrative can never again say "200 items" when it means "top 200 of an unbounded result."

## 5. Two narratives

### Easy: "Average call quality for B Himani this week"

1. **Supervisor turn begins.** Receives the user message. Prompt instructs: call `query_synthesis_specialist` first.
2. **query_synthesis_specialist** runs as a sub-agent. Reads the message + conversation history. Returns:
   ```
   {
     "rewritten_question": "Average GoodFlip Sales Call QA rubric score for agent 'B Himani', between 2026-05-05 and 2026-05-11, broken down by day",
     "classification": "answerable",
     "decomposition": [
       { "sub_question": "<same as rewritten>", "target": "data_specialist" }
     ]
   }
   ```
3. **Supervisor dispatches sub-question 1** to `data_specialist`. Specialist's prompt now contains the curated inside-sales catalog (6 tables, ~30 derived rubric columns) plus the top 3 verified queries for "average score by agent over time."
4. **data_specialist writes SQL** and calls `submit_sql` with `declared_grain=["agent", "day"]`, `expected_row_bound="small"`. Bouncer pre-check: tables allowed, no joins, aggregate at the right grain, server cap + 1 added. Executes. Post-check: 7 rows, no duplicates, no truncation. Returns chart artifact.
5. **Supervisor composes** the final answer with a time-series chart and a one-line summary.

Two specialist calls total inside the supervisor's loop. Bouncer never fires invalid. Chart is correct, truthful, and labelled with the actual row count.

### Complex: "Show me leads stuck more than 7 days and draft a follow-up email for the top 3"

1. **Supervisor turn begins.** Calls `query_synthesis_specialist`.
2. **query_synthesis_specialist** sees the target tools actually available this turn and returns:
   ```
   {
     "rewritten_question": "...",
     "classification": "answerable",
     "decomposition": [
       {
         "sub_question": "List leads whose latest_stage_observed_at is older than 7 days, sorted by mql_score desc, limit 50",
         "target": "data_specialist"
       },
       {
         "sub_question": "Draft a follow-up email template for inside-sales reps to send the top 3 stuck leads",
         "target": "authoring_specialist",
         "depends_on_sub_question": 0
       }
     ]
   }
   ```
3. **Supervisor dispatches sub-question 1** to `data_specialist`. Specialist writes SQL against `dim_lead` with `declared_grain=["lead_id"]`. Bouncer pre-check passes. Execute. Post-check: 14 rows, distinct lead_id, no duplicates. Specialist returns table artifact.
4. **Supervisor reads the top 3 lead names from the artifact** and dispatches sub-question 2 to `authoring_specialist` with those names as context. authoring_specialist returns the email draft.
5. **Supervisor composes** the final answer combining the lead table + the email draft.

Three specialist calls. The supervisor stitches them together. Two distinct domains (SQL + content generation) handled cleanly because query synthesis decomposed the question upstream.

## 6. What dies (the cleanup story)

Custom Python that exists to compensate for the workbench not existing. Delete it only after the new owner is live and every non-Sherlock caller has migrated:

- `intent_classifier.py` (143 lines of regex). Replaced by `query_synthesis_specialist` doing real classification.
- `manifest_projection.py` (236 lines of intent-keyed table filtering). Deleted entirely. The curated catalog is small enough to pass whole.
- `sql_agent.validate_sql` (regex DDL check). Replaced for Sherlock by AST + graph walk in the bouncer. If non-Sherlock callers still need a read-only SQL guard, keep a small shared wrapper there until those callers migrate.
- `sql_agent.validate_sql_columns_against_manifest` (regex column extraction). Replaced by AST in the bouncer.
- `sql_agent.SQL_GENERATION_RESPONSE_SCHEMA` (legacy, unused in v3). Deleted.
- `sql_agent.SQL_AGENT_PROMPT` (legacy, unused in v3). Deleted.
- `result_verifier.py` (81 lines, dead code). Logic absorbed into the bouncer's `check_after`.
- The silent `LIMIT 200` wrap in `execute_query`. Replaced by honest server-owned `LIMIT N+1` with `more_rows_exist`, `displayed_row_count`, and `limit_applied` propagation.
- Anywhere the prompt has SQL-hygiene rules — those move from prose into structural enforcement (the bouncer + catalog).

Net result should be less patch code and fewer policy layers: the regex modules and dead verifier disappear, while the replacement is split between the bouncer, the granularity graph, the query-synthesis specialist, and the rewritten catalogs. Do not use line counts as acceptance criteria; the acceptance bar is no legacy Sherlock call sites, deterministic enforcement, and replaying the known failure cases without a wrong chart.

## 7. What stays, augmented

- `supervisor.py` — same Agent, new prompt. Becomes pure router.
- `data_specialist.py` — same Agent. Prompt restructured around the catalog + verified queries. `submit_sql` tool body now wraps the bouncer.
- `authoring_specialist.py` — unchanged.
- `runtime.py` / `turn_orchestrator.py` — unchanged. They still drive one `Runner.run_streamed` per turn.
- `prepare_query` / `execute_query` in `sql_agent.py` — retained as low-level plumbing, not as safety policy. Tenant/app scoping and limit enforcement become bouncer-owned; execution still happens through the existing async DB path.
- The chartability gate, chart type picker, vega-lite emitter — unchanged. Their job is downstream of correct SQL and they were never the problem.

## 8. What's new

- `query_synthesis_specialist.py` — new Agent. Owns rewrite + classify + decompose. Strict structured output (Pydantic). Cheap model is fine (specialist returns text + a small structured brief; not doing heavy reasoning).
- `sql_bouncer.py` — new module. 11 deterministic rules. Pre/post-exec entry points.
- `granularity_graph.py` — new module. Built at boot from catalog.
- `semantic_models/<app>.yaml` for all three apps — rewritten to Cortex Analyst shape with mandatory physical key, analytical grain, joins, measures, JSONB-derived logical columns, and verified queries inlined.

## 9. Decisions locked

1. The LLM keeps writing SQL. We do not build a query compiler. (Discussion 2026-05-11.)
2. Catalog uses Snowflake Cortex Analyst semantic-model shape, with field names OSI-compatible where they overlap. We are not adopting OSI's multi-dialect wrapping because we ship Postgres only.
3. The Cortex Analyst granularity-graph algorithm is the bouncer's primitive. ([engineering blog](https://www.snowflake.com/en/engineering-blog/snowflake-cortex-analyst-introducting-joins-complex-schemas/))
4. Three specialists under one supervisor, all `as_tool`. No handoffs. No pre-Python.
5. `query_synthesis_specialist` owns rewrite + classify + decompose. The supervisor stays a pure router.
6. The bouncer is deterministic, lives inside the `submit_sql` FunctionTool body. Not an agent.
7. JSONB rich data is exposed as derived logical columns with Postgres extract expressions. The LLM never sees `->>` syntax. Top verified queries get `EXPLAIN` checks before rollout; expression indexes/materialization are evidence-driven, not assumed.
8. Catalog exposes facts and aggregates only. No transactional, identity, or empty tables.
9. Refusals are explicit and loud: `cannot_answer_safely` after the second bouncer-invalid in one turn. User sees the diagnostic as the refusal copy, never a wrong chart.
10. We pass the curated catalog whole. We do not retrieve over tables/columns. This is a deliberate scope choice for the curated catalog size; if an app exceeds the prompt budget later, catalog partitioning becomes a separate design.
11. Job-health visibility is one Postgres view + one route + one logs-page tab. Not a new system.
12. Per-app rollout: inside-sales first, then voice-rx, then kaira-bot. Same shape, different catalog content.
13. The bouncer must use a SQL AST parser. Regex validation is explicitly not a valid implementation of the new safety layer.
14. Query synthesis can only emit targets that are available in the supervisor toolbelt for that turn. Permission- or context-gated tools such as `authoring_specialist` must not appear in the brief when absent.

## 10. Research anchors (every claim cited in the plan doc)

- **Cortex Analyst semantic-model spec**: [docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec), [proto source of truth](https://raw.githubusercontent.com/Snowflake-Labs/semantic-model-generator/main/semantic_model_generator/protos/semantic_model.proto)
- **Cortex Analyst joins / granularity graph**: [engineering blog](https://www.snowflake.com/en/engineering-blog/snowflake-cortex-analyst-introducting-joins-complex-schemas/)
- **Cortex Analyst behind-the-scenes (multi-agent pipeline)**: [engineering blog](https://www.snowflake.com/en/engineering-blog/snowflake-cortex-analyst-behind-the-scenes/)
- **Cortex Analyst multi-turn rewriting agent**: [engineering blog](https://www.snowflake.com/en/engineering-blog/cortex-analyst-multi-turn-conversations-support/)
- **Snowflake Intelligence (orchestrator + sub-task decomposition)**: [engineering blog](https://www.snowflake.com/en/engineering-blog/inside-snowflake-intelligence-enterprise-agentic-ai/)
- **Open Semantic Interchange (OSI) v0.1.1**: [GitHub repo + spec](https://github.com/open-semantic-interchange/OSI)
- **dbt MetricFlow**: [docs](https://docs.getdbt.com/docs/build/about-metricflow)
- **Databricks Genie Agent Mode**: [Pushing the Frontier blog](https://www.databricks.com/blog/pushing-frontier-data-agents-genie)
- **Looker symmetric aggregates**: [docs](https://docs.cloud.google.com/looker/docs/reference/param-explore-symmetric-aggregates)

## 11. What this design does NOT do

- It does not introduce vector retrieval over schema tables/columns in this phase.
- It does not introduce a query compiler. The LLM writes SQL.
- It does not introduce multi-agent self-critique loops. One retry, then refuse.
- It does not introduce token-budget trimming logic.
- It does not refactor the supervisor agent into a state machine. It stays an Agents SDK `Agent` with a sharper prompt.
- It does not invent new SDK primitives. Everything uses `Agent`, `Runner.run_streamed`, `FunctionTool`, `as_tool`, `output_type`. Same toolkit as today.

End of design. The companion plan document carries the phased implementation, file-by-file diffs, and validation criteria.
