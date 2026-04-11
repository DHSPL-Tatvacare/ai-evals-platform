# Analytics Scale Plan — PostgreSQL First

> Goal: Get the DB architecture right so it scales on its own to a reasonable level, then read replica, then dedicated analytics.

## Phase 1: Denormalize + Materialize (do now)

| # | Item | What | Where | Effort |
|---|------|------|-------|--------|
| 1 | `rule_evaluations` table | Flat denormalized: one row per rule per thread. Columns: `run_id`, `thread_id`, `rule_id`, `section`, `status` (FOLLOWED/VIOLATED/NOT_APPLICABLE), `evidence_excerpt(200 chars)`, `app_id`, `tenant_id`, `created_at`. Index: `(tenant_id, app_id, rule_id, status)`. **Eliminates ALL JSONB lateral joins.** | New migration | Medium |
| 2 | `run_metrics` materialized view | Pre-computed per-run: `run_id`, `app_id`, `tenant_id`, `pass_rate`, `fail_rate`, `avg_intent_accuracy`, `thread_count`, `friction_count`, `created_at`. **One row per run, indexed.** | Migration | Small |
| 3 | `rule_metrics` materialized view | Per-rule per-app aggregate: `app_id`, `tenant_id`, `rule_id`, `section`, `total_followed`, `total_violated`, `compliance_rate`, `run_count`. **Answers "most violated rules" in one scan.** | Migration | Small |
| 4 | Missing indexes | `thread_evaluations(run_id, worst_correctness)`, `thread_evaluations(run_id, intent_accuracy)`, `eval_runs(tenant_id, app_id, status, created_at DESC)` | Migration | Tiny |
| 5 | Backfill script | Populate `rule_evaluations` from existing `thread_evaluations.result` JSONB. Idempotent, runs once. | `backend/scripts/` | Small |
| 6 | Write-path hook | When `ThreadEvaluation` is created in eval runners, also insert rows into `rule_evaluations`. Same transaction. | Eval runner | Medium |
| 7 | Refresh trigger | After run completes → `REFRESH MATERIALIZED VIEW CONCURRENTLY run_metrics, rule_metrics`. Non-blocking. | Job completion handler | Small |

## Phase 2: SQL Agent Hardening (do now)

| # | Item | What | Where | Effort |
|---|------|------|-------|--------|
| 8 | EXPLAIN cost check | Run `EXPLAIN (FORMAT JSON)` before execution. Reject if `total_cost > 50000`. Return "query too expensive" to LLM. | `sql_agent.py` | Small |
| 9 | Query result cache | In-memory dict keyed by `(sql_hash, tenant_id, app_id)`, 120s TTL. Same question = cached result. No Redis. | `sql_agent.py` | Small |
| 10 | SQL retry loop | If SQL fails, send error back to inner LLM: "fix this: {error}". One retry, then fail gracefully. | `sql_agent.py` | Small |
| 11 | Update semantic model | Point at `rule_evaluations`, `run_metrics`, `rule_metrics`. Remove JSONB lateral join patterns. Simpler SQL = fewer LLM errors = faster queries. | `semantic_model.yaml` | Small |

## Phase 3: Connection Isolation (do now, enables future)

| # | Item | What | Where | Effort |
|---|------|------|-------|--------|
| 12 | Analytics connection pool | New `analytics_session` in `database.py`. Same DB host for now, separate pool: `pool_size=3`, `statement_timeout=15s`. SQL agent uses this exclusively. **When you add a read replica, change ONE connection string.** | `database.py` + `sql_agent.py` | Small |

## Phase 4: Read Replica (when needed)

| # | Item | What | Where | Effort |
|---|------|------|-------|--------|
| 13 | PostgreSQL streaming replica | Standard PG streaming replication. Analytics pool points here. Writes go to primary, reads go to replica. | Infrastructure | DevOps |
| 14 | Replication lag handling | If materialized views are on primary, either replicate them or refresh on replica too. | Config | Small |

## Phase 5: Dedicated Analytics (when PG chokes)

| # | Item | What | Where | Effort |
|---|------|------|-------|--------|
| 15 | ClickHouse / DuckDB sidecar | Columnar engine for heavy aggregations. ETL from PG on schedule or CDC. | New service | Large |
| 16 | Time-series pre-aggregation | Hourly/daily rollups of pass rates, rule compliance, friction counts. | ETL pipeline | Medium |

---

## Performance Profile

| Query | Current (JSONB) | After Phase 1-2 |
|-------|----------------|-----------------|
| Most violated rules (cross-run) | Lateral join all threads, unpack JSON, group. **O(threads × rules)** | `SELECT FROM rule_metrics ORDER BY compliance_rate`. **O(rules)** |
| Pass rate trend | Join eval_runs + threads, count per run. **O(threads)** | `SELECT FROM run_metrics ORDER BY created_at`. **O(runs)** |
| Thread list by verdict | Index scan on worst_correctness. **OK today** | Same, **no change needed** |
| Rule compliance for 1 run | Lateral join threads for that run. **O(threads × rules)** | `SELECT FROM rule_evaluations WHERE run_id = X`. **O(rules)** |
| "How many runs total" | `COUNT(*)` on eval_runs. **OK today** | Same |
| Cross-run comparison | Two run_summary lookups. **OK today** | `SELECT FROM run_metrics WHERE run_id IN (A, B)`. **Slightly better** |

## Scale Estimates (PostgreSQL, no replica)

| Data volume | Phase 0 (now) | Phase 1-3 (after this work) |
|-------------|---------------|----------------------------|
| 10K threads, 100 runs | < 1s all queries | < 100ms all queries |
| 100K threads, 1K runs | JSONB queries 5-15s | < 500ms all queries |
| 1M threads, 10K runs | JSONB queries timeout | < 2s most queries, < 5s complex |
| 10M threads, 100K runs | Dead | Needs read replica (Phase 4) |

## Recommended Execution Order

1. Items 1-7 (schema + backfill) — do as one migration PR
2. Items 8-11 (SQL agent hardening) — do immediately after
3. Item 12 (connection pool) — do alongside, takes 30 minutes
4. Items 13-16 — when monitoring shows the choke point
