# Kaira Built-in Evaluators — Audit Overview

**Date:** 2026-02-28
**Scope:** Intent-only and correctness-only batch evaluation flows, traced end-to-end from UI submission through backend execution and result display.
**Method:** Static code trace across 7 frontend files and 8 backend files, following every data transformation from CSV upload to rendered UI.

## Documents in this directory

| File | Contents |
|------|----------|
| `OVERVIEW.md` | This file — summary and unified findings table |
| `INTENT_FLOW_ANALYSIS.md` | End-to-end trace of the intent classification evaluation pipeline |
| `CORRECTNESS_FLOW_ANALYSIS.md` | End-to-end trace of the correctness (nutritional accuracy) evaluation pipeline |
| `UNIFIED_FINDINGS.md` | All findings from both audits, consolidated and cross-referenced |

## Unified Findings Table

| # | Finding | Affects | Severity | Category |
|---|---------|---------|----------|----------|
| F1 | `success_status` always `False` when efficiency evaluator is disabled | Both | HIGH | Wrong data |
| F2 | `intent_system_prompt: null` propagates as `None` to LLM provider | Intent | MEDIUM | Fragile contract |
| F3 | Phantom correctness/efficiency counts injected into run summary when evaluator is disabled | Both | MEDIUM | Data noise |
| F4 | `is_meal_summary` false negatives silently skip correctness LLM evaluation | Correctness | MEDIUM | Silent data loss |
| F5 | `NOT APPLICABLE` phantom entries from unrelated run types pollute dashboard stats | Correctness | MEDIUM | Wrong aggregation |
| F6 | `query_type` is evaluated by LLM but never displayed in the UI | Intent | LOW | Wasted LLM compute |
| F7 | Empty `intent_query_type` ground truth yields false `is_correct_query_type=False` | Intent | LOW | Wrong data (hidden) |
| F8 | Client-side vs server-side `avg_intent_accuracy` diverge when threads have errors | Intent | LOW | Discrepancy |
| F9 | All-NOT-APPLICABLE threads show "No applicable correctness evaluations" with no diagnostic context | Correctness | LOW | UX gap |
| F10 | Underscore/space verdict normalization chain is implicit and fragile | Correctness | LOW | Tech debt |
| F11 | Image context lookback limited to 2 messages in history | Correctness | NOTE | Edge case |
| F12 | No `app_id` sent from frontend; hardcoded to `kaira-bot` in backend | Both | NOTE | Future limitation |

**Totals:** 1 HIGH, 4 MEDIUM, 5 LOW, 2 NOTE
