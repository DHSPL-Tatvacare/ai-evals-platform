# Current Architecture: Data Model & Code Map

## Data Model

### Core Tables

```
┌─────────────────────┐     ┌───────────────────────┐     ┌──────────────────────┐
│      listings       │     │      eval_runs        │     │     evaluators       │
├─────────────────────┤     ├───────────────────────┤     ├──────────────────────┤
│ id (UUID PK)        │◄────│ listing_id (FK)       │     │ id (UUID PK)         │
│ app_id              │     │ session_id (FK)       │────►│ app_id               │
│ title               │     │ evaluator_id (FK)     │────►│ listing_id (FK)      │
│ source_type         │     │ job_id (FK)           │     │ name                 │
│ audio_file (JSON)   │     │ app_id                │     │ prompt (Text)        │
│ transcript (JSON)   │     │ eval_type ◄───────────│──── │ model_id             │
│ api_response (JSON) │     │ status                │     │ output_schema (JSON) │
│ structured_outputs  │     │ config (JSON)         │     │ is_global            │
│                     │     │ result (JSON)         │     │ show_in_header       │
│                     │     │ summary (JSON)        │     │ forked_from (FK→self)│
│                     │     │ batch_metadata (JSON) │     └──────────────────────┘
│                     │     │ llm_provider          │
│                     │     │ llm_model             │
│                     │     │ duration_ms           │
└─────────────────────┘     └───────────────────────┘
                                     │
                        ┌────────────┼────────────┐
                        ▼            ▼            ▼
              ┌─────────────┐ ┌───────────┐ ┌──────────┐
              │thread_evals │ │adversarial│ │ api_logs │
              │             │ │_evals     │ │          │
              └─────────────┘ └───────────┘ └──────────┘
```

### eval_type Discriminator Values

| eval_type | App | Runner | Source FK | Description |
|-----------|-----|--------|-----------|-------------|
| `full_evaluation` | voice-rx | `voice_rx_runner.py` | `listing_id` | Standard 3-step pipeline |
| `batch_thread` | kaira-bot | `batch_runner.py` | None | Standard batch (intent+correctness+efficiency) |
| `batch_adversarial` | kaira-bot | `adversarial_runner.py` | None | Adversarial stress test |
| `custom` | both | `custom_evaluator_runner.py` | `listing_id` OR `session_id` | User-defined evaluator |
| `human` | voice-rx | (manual) | `listing_id` | Human evaluation (not automated) |

### Supporting Tables

| Table | Purpose |
|-------|---------|
| `prompts` | Versioned prompt templates, keyed by `(app_id, prompt_type, source_type, version, user_id)` |
| `schemas` | Versioned JSON schemas, same composite key |
| `jobs` | Background job queue with progress tracking |
| `settings` | Key-value config store (LLM settings, adversarial config) |
| `chat_sessions` / `chat_messages` | Kaira bot conversation data for custom evals |
| `file_records` | Audio/document file metadata and storage paths |

---

## Code Map: Backend Services

### Runner Files (Job Handlers)

```
backend/app/services/evaluators/
├── voice_rx_runner.py          # Standard voice-rx pipeline (evaluate-voice-rx)
├── batch_runner.py             # Standard kaira batch pipeline (evaluate-batch)
├── adversarial_runner.py       # Kaira adversarial pipeline (evaluate-adversarial)
├── custom_evaluator_runner.py  # Custom evaluator single-run (evaluate-custom)
├── voice_rx_batch_custom_runner.py  # Batch custom on single entity (evaluate-custom-batch)
```

> **Note**: `_save_api_log()` is duplicated identically across all 4 runner files.
> Plan: Extract to `runner_utils.py` (see Phase 1 in `04-implementation-plan.md`).

### Built-in Evaluators (Kaira Only)

```
├── intent_evaluator.py         # IntentEvaluator class — hardcoded prompt + schema
├── correctness_evaluator.py    # CorrectnessEvaluator class — hardcoded prompt + schema
├── efficiency_evaluator.py     # EfficiencyEvaluator class — hardcoded prompt + schema
├── adversarial_evaluator.py    # AdversarialEvaluator — config-driven generation + judging
├── conversation_agent.py       # Drives multi-turn conversations against live Kaira API
├── adversarial_config.py       # AdversarialConfig Pydantic model + DB load/save
├── rule_catalog.py             # Production prompt rules for correctness/efficiency/adversarial
```

### Shared Infrastructure

```
├── llm_base.py                 # BaseLLMProvider, GeminiProvider, OpenAIProvider, LoggingLLMWrapper
├── prompt_resolver.py          # {{variable}} template resolution
├── schema_generator.py         # Field-based output definitions → JSON Schema
├── response_parser.py          # Parse LLM responses (transcript, critique, JSON)
├── comparison_builder.py       # Build deep per-field comparison for API flow critique
├── evaluation_constants.py     # Hardcoded prompts + schemas for voice-rx standard pipeline
├── flow_config.py              # FlowConfig frozen dataclass for voice-rx
├── data_loader.py              # CSV → ConversationThread parsing for batch evals
├── models.py                   # In-memory dataclasses (ChatMessage, ConversationThread, etc.)
├── parallel_engine.py          # Generic parallel worker execution
├── settings_helper.py          # Read LLM settings from DB
├── kaira_client.py             # HTTP client for live Kaira API
```

### Job Worker & Dispatch

```
backend/app/services/job_worker.py
  ├── JOB_HANDLERS registry (dict of job_type → handler fn)
  ├── @register_job_handler("evaluate-voice-rx")  → voice_rx_runner
  ├── @register_job_handler("evaluate-batch")      → batch_runner
  ├── @register_job_handler("evaluate-adversarial") → adversarial_runner
  ├── @register_job_handler("evaluate-custom")      → custom_evaluator_runner
  ├── @register_job_handler("evaluate-custom-batch") → voice_rx_batch_custom_runner
  └── worker_loop() — polls jobs table every 5s
```

### Seed Defaults

```
backend/app/services/seed_defaults.py
  ├── VOICE_RX_PROMPTS (5 rows) — transcription + evaluation prompts for upload/api flows
  ├── VOICE_RX_SCHEMAS (7 rows) — transcription + evaluation schemas for upload/api flows
  ├── KAIRA_BOT_EVALUATORS (4 rows) — Chat Quality, Health Accuracy, Empathy, Risk Detection
  └── seed_all_defaults() — idempotent startup seeding
```

---

## API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/jobs` | POST | Submit background job (any type) |
| `/api/jobs/{id}` | GET | Check job status/progress |
| `/api/jobs/{id}/cancel` | POST | Cancel running/queued job |
| `/api/eval-runs` | GET | List eval runs with filters |
| `/api/eval-runs/{id}` | GET | Get single run with children |
| `/api/eval-runs/{id}/threads` | GET | Get thread evaluations for a batch run |
| `/api/eval-runs/{id}/adversarial` | GET | Get adversarial evaluations for a run |
| `/api/eval-runs/{id}/logs` | GET | Get API logs for a run |
| `/api/eval-runs/preview` | POST | Preview CSV data file statistics |
| `/api/evaluators` | GET/POST | List/create custom evaluators |
| `/api/evaluators/{id}` | GET/PUT/DELETE | CRUD on evaluators |
| `/api/evaluators/registry` | GET | List global evaluators for an app |
| `/api/evaluators/{id}/fork` | POST | Fork evaluator for a listing |
| `/api/prompts` | GET/POST/PUT | Versioned prompt management |
| `/api/schemas` | GET/POST/PUT | Versioned schema management |

---

## Frontend Feature Modules

| Module | Purpose |
|--------|---------|
| `src/features/evals/` | Custom evaluator CRUD, EvaluationOverlay, CreateEvaluatorOverlay |
| `src/features/evalRuns/` | Batch eval run list, EvalTable, thread detail, BatchCustomEvaluatorPicker, OutputFieldRenderer |
| `src/features/voiceRx/` | Voice RX listing detail, RunAllOverlay, VoiceRxRunDetail (FullEvaluationDetail + CustomEvalDetail) |
| `src/features/kaira/` | Kaira bot session view, KairaBotEvaluatorsView |
| `src/features/listings/` | Listing list/detail for voice-rx |
| `src/features/transcript/` | Transcript viewer/editor |

### Key Frontend Infrastructure

| Component | File | Purpose |
|-----------|------|---------|
| `VariablePickerPopover` | `src/components/ui/VariablePickerPopover.tsx` | Variable insertion in prompt editor. **Currently reads from hardcoded `variableRegistry.ts`; will migrate to backend API.** |
| `variableRegistry.ts` | `src/services/templates/variableRegistry.ts` | **Hardcoded duplicate** of backend variable metadata (395 lines). **To be deleted** after backend registry + API exists. |
| `apiVariableExtractor.ts` | `src/services/templates/apiVariableExtractor.ts` | Extracts `rx.*` paths client-side. **To be deleted** — replaced by backend endpoint. |
| `OutputFieldRenderer` | `src/features/evalRuns/components/OutputFieldRenderer.tsx` | Schema-driven rendering of custom eval output (card/inline/badge modes) |
| `useSubmitAndRedirect` | `src/hooks/useSubmitAndRedirect.ts` | Submit job → track → poll for run_id → redirect to RunDetail |
| `JobCompletionWatcher` | `src/components/JobCompletionWatcher.tsx` | Polls active jobs, shows completion toasts |
| `evaluatorExecutor.ts` | `src/services/evaluators/evaluatorExecutor.ts` | Single custom eval submission + polling |

---

## Pipeline Flow Diagrams

### Voice RX Standard Pipeline

```
Frontend (RunAllOverlay)
  │
  ▼ POST /api/jobs { job_type: "evaluate-voice-rx", params: { listing_id, prerequisites, model } }
  │
  ▼ Job Worker picks up job
  │
  ▼ voice_rx_runner.run_voice_rx_evaluation(job_id, params)
  │
  ├─► FlowConfig.from_params(params, listing.source_type)
  │
  ├─► _load_default_prompt(app_id, "transcription", flow_type)     ◄── DB defaults
  ├─► _load_default_schema(app_id, "transcription", flow_type)     ◄── DB defaults
  │
  ├─► Step 1: _run_transcription(flow, llm, listing, audio, prompt, schema)
  │     └─► llm.generate_with_audio(prompt, audio, schema)         ◄── AUDIO input
  │
  ├─► Step 2: _run_normalization(flow, llm, listing, prerequisites) [optional]
  │     └─► llm.generate_json(prompt, schema)                      ◄── TEXT only
  │
  ├─► Step 3: _run_critique(flow, llm, listing, prerequisites, evaluation)
  │     ├─► Server builds comparison table (segments or fields)
  │     ├─► UPLOAD_EVALUATION_PROMPT / API_EVALUATION_PROMPT       ◄── HARDCODED
  │     ├─► UPLOAD_EVALUATION_SCHEMA / API_EVALUATION_SCHEMA       ◄── HARDCODED
  │     └─► llm.generate_json(prompt, schema)                      ◄── TEXT only, NO audio
  │
  ├─► _build_summary(flow, evaluation)                             ◄── SERVER-SIDE stats
  │
  └─► UPDATE eval_runs SET result=..., summary=..., status='completed'
```

### Kaira Bot Batch Pipeline

```
Frontend (Batch Eval Form)
  │
  ▼ POST /api/jobs { job_type: "evaluate-batch", params: { csv_content, evaluator toggles, custom_evaluator_ids } }
  │
  ▼ Job Worker picks up job
  │
  ▼ batch_runner.run_batch_evaluation(job_id, ...)
  │
  ├─► DataLoader(csv_content) → parse threads
  │
  ├─► For each thread (parallel or sequential via run_parallel):
  │     │
  │     ├─► IntentEvaluator.evaluate_thread(messages)       [if enabled]
  │     │     └─► Hardcoded INTENT_JSON_SCHEMA, system_prompt
  │     │
  │     ├─► CorrectnessEvaluator.evaluate_thread(thread)    [if enabled]
  │     │     └─► Hardcoded CORRECTNESS_JUDGE_PROMPT + rules from rule_catalog
  │     │
  │     ├─► EfficiencyEvaluator.evaluate_thread(thread)     [if enabled]
  │     │     └─► Hardcoded EFFICIENCY_JUDGE_PROMPT + rules from rule_catalog
  │     │
  │     ├─► Custom evaluators (for each custom_evaluator_id):
  │     │     ├─► resolve_prompt(evaluator.prompt, {messages: interleaved})
  │     │     ├─► generate_json_schema(evaluator.output_schema)
  │     │     └─► llm.generate_json(resolved_prompt, json_schema)
  │     │
  │     └─► INSERT thread_evaluations (per-thread results)
  │
  └─► UPDATE eval_runs SET summary=..., status='completed'
```

### Custom Evaluator Pipeline (Single)

```
Frontend (EvaluationOverlay or KairaBotEvaluatorsView)
  │
  ▼ POST /api/jobs { job_type: "evaluate-custom", params: { evaluator_id, listing_id|session_id, app_id } }
  │
  ▼ Job Worker picks up job
  │
  ▼ custom_evaluator_runner.run_custom_evaluator(job_id, params)
  │
  ├─► Load Evaluator from DB (prompt, output_schema, model_id)
  │
  ├─► Load entity (Listing for voice-rx, ChatSession+Messages for kaira-bot)
  │
  ├─► resolve_prompt(evaluator.prompt, context)
  │     └─► {{chat_transcript}} → formatted messages
  │     └─► {{transcript}} → listing transcript
  │     └─► {{audio}} → marker (audio attached separately)
  │     └─► {{structured_output}} → listing.api_response.rx
  │
  ├─► generate_json_schema(evaluator.output_schema)
  │
  ├─► llm.generate_json(prompt, schema) or llm.generate_with_audio(...)
  │
  ├─► _extract_scores(output, output_schema) → summary
  │
  └─► UPDATE eval_runs SET result={output, rawRequest, rawResponse}, summary=scores
```
