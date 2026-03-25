# Custom Seed Evaluators — Overview

**Created:** 2026-02-24
**Goal:** Add 5 seeded medical quality evaluators for voice-rx (both upload and API flows), clean up the variable registry, and provide a frictionless "Add recommended" UX.

## Problem

Voice-rx has zero seeded evaluators. Users must create custom evaluators from scratch every time. The variable registry is cluttered with redundant and pipeline-internal variables that confuse users. This creates unnecessary friction and makes the custom evaluator feature feel unfinished.

## Solution

1. **Clean up the variable registry** — Remove redundant API-accessor variables (replaced by dynamic path resolution), remove pipeline-internal variables (preferences used only in standard eval), rename for clarity.
2. **Add 10 seed evaluator definitions** — 5 for upload flow, 5 for API flow, covering the same 5 medical quality metrics. Created directly on listings via a new endpoint (no global DB seeds, no registry pollution).
3. **Add "Add recommended" UX** — Prominent button in EvaluatorsView empty state. One click creates 5 evaluators matching the listing's source_type.

## The 5 Metrics

| # | Metric | What It Measures | Score Type |
|---|---|---|---|
| 1 | Medical Entity Recall (MER) | % of clinical entities in audio captured in output | number 0-100 |
| 2 | Factual Integrity | % of extracted data points traceable to source | number 0-100 |
| 3 | Negation Consistency | Accuracy of mapping denied/excluded conditions | number 0-100 |
| 4 | Temporal Precision | Accuracy of timelines, durations, frequencies | number 0-100 |
| 5 | Critical Safety Audit | Whether high-risk symptoms were captured | boolean pass/fail |

## Variable Design Per Flow

**Upload flow** — evaluates transcript quality against audio:
- `{{audio}}` — the audio recording
- `{{transcript}}` — the uploaded transcript (the thing being evaluated)

**API flow** — evaluates structured extraction quality against audio + transcript:
- `{{audio}}` — the audio recording
- `{{input}}` — transcript from API response (dynamic path → `api_response["input"]`)
- `{{rx}}` — structured extraction from API response (dynamic path → `api_response["rx"]`)

No new abstraction variables. Existing variables + dynamic path resolution handle both flows.

## Phase Summary

| Phase | Goal | Risk | Files Changed |
|---|---|---|---|
| **Phase 1: Variable Registry Cleanup** | Remove clutter, rename for clarity, expand dynamic paths | Low — display changes + removing dead code | `variable_registry.py`, `prompt_resolver.py`, `evaluators.py` (routes) |
| **Phase 2: Seed Evaluators + UX** | 10 seed definitions, new endpoint, "Add recommended" button | Medium — new endpoint, new UI element, prompt design | `seed_defaults.py`, `evaluators.py` (routes+schemas), `custom_evaluator_runner.py`, `evaluatorsApi.ts`, `evaluatorsStore.ts`, `EvaluatorsView.tsx` |

## Key Design Decisions

1. **Direct creation, not global seeds.** Evaluator definitions live as code constants. A new endpoint creates listing-scoped evaluators directly. No global DB seeds, no registry browsing, no forking step. Simpler than the kaira-bot pattern and avoids polluting the registry.

2. **No new variables.** Upload flow uses `{{audio}}` + `{{transcript}}`. API flow uses `{{audio}}` + dynamic paths (`{{input}}`, `{{rx}}`). The existing dynamic path resolver handles API response navigation.

3. **No backward compatibility.** Old variable names (`api_input`, `structured_output`, `api_rx`, `llm_transcript`, `llm_structured`) are removed from both registry and resolver. Existing user data will be cleaned up manually.

4. **No dependency on standard eval.** Seed evaluators use only independent variables. They run via `evaluate-custom` / `evaluate-custom-batch` job types, completely separate from the standard pipeline.

5. **Source-type awareness lives server-side.** The seed endpoint reads the listing's `source_type` and creates the matching 5 evaluators. Frontend just calls one endpoint.

## Invariants

1. Standard voice-rx pipeline must still work — pipeline-internal variable RESOLUTION stays in `prompt_resolver.py`, only the REGISTRY visibility is removed.
2. Kaira-bot evaluators are untouched — `{{chat_transcript}}` and all kaira-bot seeds remain as-is.
3. Existing custom evaluator run flows (`evaluate-custom`, `evaluate-custom-batch`) are unchanged — same job types, same runner, same polling.
4. Batch runner's internal custom evaluator path (for kaira-bot `evaluate-batch`) is unchanged.
5. RunAllOverlay, single-run flow, job polling — all unchanged.

## Detailed Plans

- [Phase 1: Variable Registry Cleanup](./PHASE_1_VARIABLE_CLEANUP.md)
- [Phase 2: Seed Evaluators + UX](./PHASE_2_SEED_EVALUATORS.md)
