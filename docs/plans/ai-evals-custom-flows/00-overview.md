# AI Evals Platform: Standard vs Custom Evaluation Flows

## Document Index

| # | Document | Purpose |
|---|----------|---------|
| 00 | **This file** | Executive overview, current state, goals, what exists, what's missing |
| 01 | `01-architecture-current-state.md` | Full data model & code map of existing pipelines |
| 02 | `02-voice-rx-vs-kaira-comparison.md` | Side-by-side comparison of both apps' eval flows |
| 03 | `03-variable-registry-design.md` | Variable registry as single source of truth, schema builder enhancements |
| 04 | `04-implementation-plan.md` | Phased implementation plan with concrete file changes |
| 05 | `05-custom-runner-consolidation.md` | Merge custom runners, unify BE/FE/poll contract |

---

## The Core Problem

The platform has **two distinct evaluation philosophies** that currently occupy overlapping code paths with ad-hoc boundaries:

1. **Standard/Built-in evaluations** — Hardcoded, reproducible, quality-controlled pipelines that represent the "faithful" ground-truth assessment of a system. Prompts, schemas, and comparison logic are controlled by engineers, not end-users.

2. **Custom evaluations** — User-defined evaluators with arbitrary prompts, schemas, and template variables that allow experimentation without polluting the standard pipeline.

The **divergence** is that these two modes share some infrastructure (LLM providers, `EvalRun` model, job worker) but have no shared contract for **what constitutes a pipeline step**, no formal **variable registry**, and no clear boundary between "standard pipeline artifacts" and "user-configurable artifacts."

Additionally, the **custom evaluator flow is a second-class citizen**: the batch custom path (`RunAllOverlay`) has no job tracking, no polling, no redirect — unlike every standard flow.

---

## Current State Summary

### Voice RX Standard Pipeline
- **Type**: `full_evaluation` (eval_type on EvalRun)
- **Runner**: `voice_rx_runner.py`
- **Pipeline**: 3-step frozen FlowConfig → Transcription → Normalization (optional) → Critique
- **Prompts**: Transcription prompt loaded from DB defaults; Evaluation prompt **hardcoded** in `evaluation_constants.py`
- **Schemas**: Transcription schema from DB defaults; Evaluation schema **hardcoded**
- **Key constraint**: Critique step is text-only (never receives audio), uses server-built comparison tables, statistics computed server-side
- **Variables**: `{{segment_count}}`, `{{time_windows}}`, `{{language_hint}}`, `{{script_preference}}`, etc. — resolved by `prompt_resolver.py`

### Kaira Bot Standard Pipeline (Batch Evals)
- **Type**: `batch_thread` (eval_type on EvalRun)
- **Runner**: `batch_runner.py`
- **Pipeline**: Per-thread: Intent → Correctness → Efficiency (all optional toggles)
- **Prompts**: Hardcoded in each evaluator class (`IntentEvaluator`, `CorrectnessEvaluator`, `EfficiencyEvaluator`)
- **Schemas**: Hardcoded JSON schemas in each evaluator class
- **Key constraint**: Rule-driven via `rule_catalog.py`; production prompt rules injected into judge prompts
- **Variables**: Thread data loaded from CSV via `DataLoader`, formatted into evaluator prompts internally

### Kaira Bot Adversarial Pipeline
- **Type**: `batch_adversarial` (eval_type on EvalRun)
- **Runner**: `adversarial_runner.py`
- **Pipeline**: Generate test cases → Run conversations against live Kaira API → Judge transcripts
- **Config**: `AdversarialConfig` (categories + rules) stored in settings table, Pydantic-validated
- **Key constraint**: Data-driven categories and rules from DB config

### Custom Evaluator Pipeline
- **Type**: `custom` (eval_type on EvalRun)
- **Runner**: `custom_evaluator_runner.py` (single) / `voice_rx_batch_custom_runner.py` (batch)
- **Pipeline**: Load evaluator → Resolve template variables → Generate JSON schema from field definitions → Single LLM call
- **Prompts**: User-defined (stored in `evaluators.prompt`)
- **Schemas**: Field-based definitions (`evaluators.output_schema`) → converted to JSON Schema at runtime by `schema_generator.py`
- **Variables**: `{{chat_transcript}}`, `{{transcript}}`, `{{audio}}`, `{{structured_output}}`, etc. — resolved by `prompt_resolver.py`

---

## Key Divergences

| Dimension | Voice RX Standard | Kaira Batch Standard | Custom Evaluators |
|-----------|-------------------|---------------------|-------------------|
| Prompt source | DB defaults + hardcoded | Hardcoded in evaluator classes | User-defined in `Evaluator.prompt` |
| Schema source | DB defaults + hardcoded | Hardcoded in evaluator classes | Field-based → JSON Schema at runtime |
| Variable resolution | `prompt_resolver.py` (partial) | Internal formatting per evaluator | `prompt_resolver.py` (full) |
| Pipeline steps | Multi-step (transcribe → normalize → critique) | Multi-evaluator per thread | Single LLM call |
| Result shape | `EvalRun.result` as structured dict | `ThreadEvaluation.result` as nested evaluator outputs | `EvalRun.result.output` as user-defined shape |
| Summary shape | Server-computed accuracy/severity | Aggregated verdicts/accuracy across threads | `_extract_scores()` from output schema |
| Config snapshot | Stored in `EvalRun.config` | Stored in `EvalRun.batch_metadata` | Stored in `EvalRun.config` |

---

## The Goal

Create a clean separation with a robust custom eval pipeline that matches the quality of standard flows:

```
┌─────────────────────────────────────────────────────────┐
│                    Standard Pipeline                     │
│  Hardcoded prompts/schemas/logic. Never user-editable.  │
│  "This is what the system IS doing."                     │
│                                                         │
│  Voice RX: transcribe → normalize → critique            │
│  Kaira: intent → correctness → efficiency               │
│  Kaira Adversarial: generate → converse → judge         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    Custom Pipeline                        │
│  User-defined prompts/schemas. Experiment freely.        │
│  "This is what I want to EXPLORE."                       │
│                                                         │
│  Variable Registry: single source of truth (backend)    │
│  Schema Builder: visual output definition + enum type   │
│  Score Engine: _extract_scores with explicit field roles │
│  Full Job Contract: submit → poll → track → redirect    │
│  Same RunDetail experience as standard evals             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   Shared Infrastructure                   │
│  EvalRun model, Job worker, LLM providers, ApiLog,      │
│  parallel_engine, prompt_resolver, schema_generator,     │
│  runner_utils (extracted shared code)                    │
└─────────────────────────────────────────────────────────┘
```

---

## What's Already In Place (Strengths)

1. **Unified EvalRun model** — Single source of truth for all evaluation types via `eval_type` discriminator
2. **Job worker with typed dispatch** — Clean handler registry pattern
3. **LLM abstraction** — `BaseLLMProvider` + `LoggingLLMWrapper` with provider-agnostic interface
4. **Template variable resolver** — `prompt_resolver.py` handles `{{variable}}` substitution
5. **Schema generator** — `schema_generator.py` converts field definitions to JSON Schema
6. **FlowConfig** — Immutable dataclass controlling Voice RX pipeline behavior
7. **AdversarialConfig** — Pydantic-validated, DB-stored config for adversarial categories/rules
8. **Config snapshots** — Each EvalRun stores the full config used at execution time
9. **Custom evaluators in batch** — `batch_runner.py` already runs custom evaluators alongside built-ins per thread
10. **Frontend variable registry exists** — `variableRegistry.ts` with `TEMPLATE_VARIABLES`, `getVariablesForApp()`, `validatePromptVariables()`, step-aware filtering, and `VariablePickerPopover` UI
11. **OutputFieldRenderer** — Schema-driven rendering of custom eval results (card/inline/badge modes)
12. **VoiceRxRunDetail CustomEvalDetail** — Already renders custom eval output with scores, breakdown, reasoning
13. **Kaira RunDetail CustomEvaluationsBlock** — Already renders custom eval output inside batch thread detail
14. **Evaluator name in run lists** — `getEvalRunName()` extracts name from `summary.evaluator_name` or `config.evaluator_name`

## What's Missing

1. **Backend variable registry** — Variables are scattered across `prompt_resolver.py` as ad-hoc if/elif chains; frontend has a hardcoded duplicate in `variableRegistry.ts`; no single source of truth
2. **No API to fetch variables** — Frontend hardcodes its own copy of the registry instead of fetching from backend
3. **No prompt validation endpoint** — No way to validate a prompt server-side before running
4. **Broken batch custom poll contract** — `RunAllOverlay` fires `evaluate-custom-batch` with no polling, no job tracking, no redirect — unlike every standard flow
5. **Split custom runner files** — `custom_evaluator_runner.py` and `voice_rx_batch_custom_runner.py` are two files for one concept; the batch file is a thin wrapper
6. **`_save_api_log()` duplicated 4x** — Identical function copy-pasted in 4 runner files
7. **`_extract_scores()` is fragile** — Uses substring matching for "reasoning" fields (`"reason"`, `"explanation"`, `"comment"`); guesses `max_score` from `thresholds.green` or defaults to 100; no explicit field roles
8. **No `enum` field type** — Schema builder only supports `number | text | boolean | array`; no constrained enum/select type for verdicts, meaning LLM can return any string and `VerdictBadge` has to guess via heuristics
9. **`RunAllOverlay` is voice-rx only** — Component has `listingId` prop but no `sessionId`; Kaira sessions can't trigger batch custom evals from their UI
10. **No "custom-only" batch mode for Kaira** — Can't run only custom evaluators on a data file without also running intent/correctness/efficiency
