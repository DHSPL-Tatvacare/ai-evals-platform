# AI Evals Platform — Project 101

Guided reference for this codebase. Covers what the platform is, why it exists, and how it works — following real user flows through all layers. Read this end to end for a faithful picture.

---

## What Is This?

AI Evals Platform is a full-stack evaluation system for AI outputs used in production clinical and conversational workflows. It gives QA teams a structured, reproducible way to measure, compare, and audit AI model performance — backed by a versioned prompt and schema system, a background job pipeline, and a unified result store.

Two active workspaces:

- **Voice Rx** (`voice-rx`): Evaluates medical transcription quality. Users upload audio files with reference transcripts and run a two-call LLM pipeline to assess accuracy at the segment level.
- **Kaira Bot** (`kaira-bot`): Evaluates conversational AI quality. Users test chat sessions against custom or built-in evaluators, run bulk thread evaluations from CSV, and execute automated adversarial tests.

---

## Why Does It Exist?

### Problems It Solves

**Manual QA is inconsistent.** Human reviewers apply different standards session to session. Results cannot be reproduced, compared across runs, or shared as evidence.

**AI outputs need structured evidence, not just scores.** A pass/fail score alone is not actionable. Teams need to know what failed, which segment caused it, and why — in a format that can be referenced and re-evaluated.

**Audit trails matter in clinical workflows.** Decisions backed by AI outputs must be traceable. Every evaluation run, LLM call, and prompt version is stored and queryable.

**Scaling evaluation beyond human reviewers.** Batch thread evaluation and adversarial testing automate coverage that would otherwise take days of manual effort.

### Core Philosophy

- Evidence over intuition: every evaluation is reproducible and auditable.
- Structured by default: prompts, schemas, and versioning are first-class concerns.
- Async by design: long-running evaluations execute as background jobs with progress tracking and cancellation support.
- Actionable outcomes: results are designed to support QA decisions, not just model diagnostics.

---

## How It Works

### The Universal 4-Step Workflow

Every evaluation on this platform follows the same pattern regardless of workspace:

1. **Bring Assets** — upload audio, transcripts, or CSV data; or connect an API source.
2. **Review Setup** — configure prompts, schemas, and LLM provider/model settings.
3. **Run Evaluators** — execute standalone custom evaluators against a single session or listing.
4. **Run Full Evals** — launch a complete multi-step evaluation pipeline as a background job.

---

### Workspace: Voice Rx

Evaluates medical audio transcription quality against a reference transcript.

**Two-call pipeline, always in this order:**

1. **Transcription call** — LLM receives audio and generates a transcript. Supports multilingual input. Media is passed inline via `Part.from_bytes()` (Vertex AI does not support file upload).
2. **Critique call** — LLM compares the AI-generated transcript against the reference transcript. This step is text-only (`generate_json`). No audio is sent on this call. Outputs segment-level findings and an aggregate critique.

Statistics (word error rate, segment counts, etc.) are computed server-side from stored records. The LLM is never asked to self-report counts.

**Job type:** `evaluate-voice-rx`

**Eval type stored:** `full_evaluation`

---

### Workspace: Kaira Bot

Evaluates conversational AI quality across live chat sessions, bulk thread exports, and automated adversarial probes.

**Three evaluation modes:**

| Mode | Job type | Input | Output |
|------|----------|-------|--------|
| Custom evaluator run | `evaluate-custom` / `evaluate-custom-batch` | Single session or listing | EvalRun with structured JSON output |
| Batch thread evaluation | `evaluate-batch` | CSV of conversation threads | ThreadEvaluation rows + aggregate EvalRun |
| Adversarial evaluation | `evaluate-adversarial` | Target Kaira API + test config | AdversarialEvaluation rows + aggregate EvalRun |

Adversarial evaluation hits the live Kaira API, generates adversarial probes, simulates conversations, and scores safety and compliance at the case level. Results are stored for replay and trend tracking.

---

### Built-in Evaluators

Three evaluators are seeded on startup for both apps from `backend/app/services/seed_defaults.py`:

| Evaluator | Purpose |
|-----------|---------|
| Intent | Classifies whether the AI response addressed the user's stated intent |
| Correctness | Assesses factual or clinical accuracy of the response |
| Efficiency | Evaluates workflow efficiency and response conciseness |

These are stored in the `evaluators` table and are available immediately after first run.

---

### Custom Evaluators

Users define their own evaluators by writing a prompt and a JSON output schema. The platform executes the prompt against the target content (listing or chat session), calls the LLM, and validates the output against the schema. Results are stored as a `custom` EvalRun.

This is the primary extensibility mechanism. Any evaluation criterion — tone, compliance language, clinical accuracy, brand voice — can be codified as an evaluator and versioned.

---

### Report Generation

After evaluation runs complete, a report pipeline can generate:

- Per-run AI narrative summarizing findings
- Health scores across evaluation dimensions
- Cross-run analytics comparing trends across multiple runs

Reports are cached in the `evaluation_analytics` table (scope: `single_run` per run, `cross_run` per app). Force regen with `?refresh=true` on the report endpoints.

- Per-run report: `GET /api/reports/{run_id}`
- Cross-run analytics: `GET /api/reports/cross-run-analytics` / `POST /api/reports/cross-run-analytics/refresh`

Job types: `generate-report`, `generate-cross-run-report`

---

## Key Abstractions

### 1. LLM Provider Layer

**Location:** `backend/app/services/evaluators/llm_base.py`

All LLM calls go through provider wrappers. Evaluation runners never call SDKs directly. This is a hard rule — not a preference.

**Four providers:**

| Provider | Auth | Notes |
|----------|------|-------|
| `GeminiProvider` | Vertex AI service account (jobs) or API key (settings generation) | Model families 2.0, 2.5, 3+ have different thinking config params |
| `OpenAIProvider` | API key | Async via `asyncio.to_thread()` |
| `AzureOpenAIProvider` | Azure API key + endpoint | Inherits OpenAI provider |
| `AnthropicProvider` | API key | Full retry and timeout support |

**Gemini auth modes — critical distinction:**
- Service account (Vertex AI): used for all backend evaluation jobs. Reliable for long-running tasks. Does not support `client.files.upload()` — use `Part.from_bytes()` for media.
- API key (Developer API): used for frontend-triggered tasks (Settings prompt/schema generation). Supports file upload.

**Gemini thinking config:**
- Model family 2.5: use `thinking_budget` (integer)
- Model family 3+: use `thinking_level` (enum string)
- These are mutually exclusive. Wrong param = 400 error.
- To disable thinking on Vertex AI: omit `thinking_config` entirely. `thinking_budget=0` is rejected by Vertex.

**Timeout tiers:**

| Tier | Timeout | Use case |
|------|---------|----------|
| `text_only` | 60s | Text generation |
| `with_schema` | 90s | Structured JSON output |
| `with_audio` | 180s | Audio transcription |
| `with_audio_and_schema` | 240s | Audio + structured output |

**Retry architecture:** Two-layer — SDK-native retries (4–5 attempts) plus app-level `_with_retry` safety net. Per-attempt timeout runs inside `_with_retry`, not wrapping it. This means a `retry-after: 45s` delay does not compete with a 60s timeout.

---

### 2. Job Execution Pipeline

**Location:** `backend/app/services/job_worker.py`

Any operation taking more than a few seconds runs as a background job using a handler registry pattern:

```python
@register_job_handler("evaluate-voice-rx")
async def handle_evaluate_voice_rx(job, session):
    ...
```

**7 registered handlers:**

1. `evaluate-voice-rx` — Voice Rx two-call transcription + critique pipeline
2. `evaluate-batch` — Batch thread evaluation from CSV
3. `evaluate-adversarial` — Adversarial test execution against live Kaira API
4. `evaluate-custom` — Single custom evaluator run
5. `evaluate-custom-batch` — Batch custom evaluator run
6. `generate-report` — Per-run report generation
7. `generate-cross-run-report` — Cross-run analytics generation

**Safety features built into the worker:**
- Cooperative cancellation via `is_job_cancelled()` checks at natural checkpoints in long-running flows.
- Progress tracking via `update_job_progress()` for frontend polling feedback.
- Stale job recovery on startup — jobs stuck longer than 15 minutes are recovered automatically.
- Orphaned eval_run reconciliation on startup.

---

### 3. Frontend Job Polling

**Location:** `src/services/api/jobPolling.ts`

`submitAndPollJob()` is the single abstraction for the entire async job lifecycle. It handles job creation, polling, cancellation, abort, and retry internally. Components call this and navigate to the result on completion.

No component should implement its own polling loop. This is the primary pattern violation to watch for.

---

### 4. EvalRun — Central Data Entity

Every evaluation outcome, regardless of workspace or type, is one `EvalRun` record. The `eval_type` field determines the shape of the `result` JSON column:

```
eval_type: full_evaluation    → Voice Rx two-call result with segment findings
eval_type: custom             → Single custom evaluator structured output
eval_type: human              → Manual annotation/review
eval_type: batch_thread       → Kaira batch thread aggregate summary
eval_type: batch_adversarial  → Adversarial test aggregate summary
```

FK/cascade chain: `listings`/`chat_sessions` → `eval_runs` → `thread_evaluations`/`adversarial_evaluations`/`api_logs`

This chain must not be broken. Deleting a listing or chat session cascades down. Deleting an eval_run cleans up its dependent records.

---

## Architecture

```
Browser (React)                         Server (FastAPI)                    Database
┌───────────────────────┐  HTTP/JSON   ┌──────────────────────────┐       ┌──────────┐
│  UI Components         │────────────>│  API Routers (16)         │──────>│          │
│  Zustand Stores (14)   │<────────────│  Services / Evaluators    │<──────│ Postgres │
│  API Client Layer      │             │  Job Worker (7 handlers)  │       │  (JSONB) │
└───────────────────────┘             │  LLM Providers (4)        │       └──────────┘
         :5173                        └──────────────────────────┘
                                                :8721
```

The frontend never calls LLM APIs directly. All evaluation logic, LLM calls, and data persistence run through the FastAPI backend. The frontend is a thin client.

---

## Frontend Structure (`src/`)

```
src/
├── app/               <- App shell, routing, page components
├── components/ui/     <- Generic UI primitives (Button, Modal, Badge, etc.)
├── config/            <- Route constants, app configuration
├── constants/         <- Hardcoded values, default configs
├── features/          <- Domain-specific modules (see below)
├── hooks/             <- Reusable React hooks
├── services/
│   ├── api/           <- HTTP client + per-resource API modules + jobPolling
│   ├── storage/       <- Barrel re-export from api/ (backward compat)
│   ├── notifications/ <- Toast notifications via notificationService
│   └── logger/        <- Structured diagnostic logging
├── stores/            <- Zustand stores (14 stores + index barrel)
├── styles/            <- Tailwind v4 globals + CSS variables (design tokens)
├── types/             <- TypeScript interfaces and type definitions
└── utils/             <- Pure helpers (cn, date parsing, etc.)
```

**Feature modules (`src/features/`):**

| Feature | Purpose |
|---------|---------|
| `voiceRx` | Voice Rx dashboard, run list, run detail, settings |
| `evalRuns` | Shared evaluation dashboard, run list, run detail (used by kaira-bot) |
| `kaira` | Chat interface, message tagging, trace analysis, action buttons |
| `kairaBotSettings` | Kaira-specific settings and tag management |
| `settings` | LLM provider config, prompt/schema editors, model selection |
| `upload` | File upload with drag-and-drop, CSV preview, validation |
| `transcript` | Transcript viewer with segment-level display and audio alignment |
| `structured-outputs` | JSON viewer, schema validator, structured output comparison |
| `evals` | Metric displays, comparison cards, evaluation statistics |
| `export` | PDF/CSV/JSON export with format selectors |
| `listings` | Listing cards, list views, detail views |
| `common` | Shared cross-feature UI components |

**Zustand stores (14):** appStore, appSettingsStore, llmSettingsStore, globalSettingsStore, listingsStore, schemasStore, promptsStore, evaluatorsStore, chatStore, uiStore, miniPlayerStore, taskQueueStore, jobTrackerStore, crossRunStore

**Critical Zustand pattern:**

```typescript
// Correct — re-renders only when this slice changes
const prompts = usePromptsStore((s) => s.prompts['voice-rx']);

// Wrong — re-renders on any store mutation
const store = usePromptsStore();
```

**API client modules (`src/services/api/`):**

| Module | Purpose |
|--------|---------|
| `client.ts` | Shared HTTP client (`apiRequest`, `apiUpload`, `apiDownload`) |
| `jobPolling.ts` | `submitAndPollJob()` — async job lifecycle abstraction |
| `listingsApi.ts`, `filesApi.ts`, `promptsApi.ts`, `schemasApi.ts` | Resource CRUD |
| `evaluatorsApi.ts`, `evalRunsApi.ts`, `chatApi.ts`, `jobsApi.ts` | Domain resources |
| `settingsApi.ts`, `tagsApi.ts`, `adversarialConfigApi.ts`, `historyApi.ts` | Supporting resources |
| `reportsApi.ts` | Report fetching and refresh |

---

## Backend Structure (`backend/`)

```
backend/app/
├── main.py                    <- FastAPI app, router registration (16 routers), lifespan hooks
├── database.py                <- Async SQLAlchemy engine + session factory
├── config.py                  <- All config from env vars (pydantic-settings)
├── models/                    <- 16 ORM models (SQLAlchemy 2 Mapped[] style)
├── schemas/                   <- Pydantic request/response schemas (CamelModel)
├── routes/                    <- 16 API routers
└── services/
    ├── evaluators/            <- llm_base.py providers + evaluation runners
    ├── reports/               <- Report aggregation, AI narrative, health scores
    ├── job_worker.py          <- Background job dispatch + handler registry
    ├── seed_defaults.py       <- Startup seeding (prompts, schemas, evaluators)
    └── evaluation_constants.py <- System prompts, normalization templates
```

**ORM tables (16):** eval_runs, jobs, listings, files, prompts, schemas, evaluators, chat_sessions, chat_messages, history, settings, tags, thread_evaluations, adversarial_evaluations, api_logs, evaluation_analytics

**API routers (16):** listings, files, prompts, schemas, evaluators, chat, history, settings, tags, jobs, eval_runs, threads, llm, adversarial_config, admin, reports

**Evaluation runners (`backend/app/services/evaluators/`):**

| Runner | Purpose |
|--------|---------|
| `voice_rx_runner.py` | Two-call transcription + critique pipeline |
| `custom_evaluator_runner.py` | Execute user-defined evaluator prompt + schema |
| `batch_runner.py` | CSV-based batch processing for threads and adversarial |
| `intent_evaluator.py` | Intent classification |
| `correctness_evaluator.py` | Correctness assessment |
| `efficiency_evaluator.py` | Efficiency/workflow evaluation |
| `adversarial_evaluator.py` | Adversarial probe execution |

**Seed defaults (`seed_defaults.py`):**

On startup the backend seeds defaults for both apps if they don't exist:
- Voice Rx: 5 prompts, 3 schemas, 3 evaluators (Intent, Correctness, Efficiency)
- Kaira Bot: 2 prompts, 1 schema, 3 evaluators (Intent, Correctness, Efficiency)

---

## Data Flows

### Voice Rx Full Evaluation

```
1. UPLOAD
   FileDropZone component
   └── filesApi.upload()
       └── POST /api/files
           └── FileRecord saved, file written to disk/blob

2. CREATE LISTING
   ListingCard component
   └── listingsApi.create()
       └── POST /api/listings
           └── Listing row with file references

3. RUN EVALUATION
   RunAllOverlay component
   └── submitAndPollJob("evaluate-voice-rx", params)
       └── POST /api/jobs → Job created (status: queued)
           job_worker picks up job:
           ├── Call 1: GeminiProvider.generate() with audio (Part.from_bytes)
           │         System prompt: multilingual, script-aware
           ├── Call 2: GeminiProvider.generate_json() text-only
           │         Compares AI transcript vs reference
           ├── EvalRun saved (eval_type: full_evaluation)
           ├── ApiLog entries saved (one per LLM call)
           └── Job status: completed
       Frontend polls GET /api/jobs/:id → navigates to /runs/:runId

4. VIEW RESULTS
   VoiceRxRunDetail page
   └── evalRunsApi.getById()
       └── GET /api/eval-runs/:id
           └── Returns EvalRun with segment-level findings + aggregate stats
```

### Kaira Batch Thread Evaluation

```
1. User uploads thread CSV via upload interface
2. submitAndPollJob("evaluate-batch", { listingId, evaluatorIds, ... })
3. POST /api/jobs → Job queued
4. job_worker dispatches to batch_runner
5. batch_runner iterates CSV rows:
   └── Per thread: run each evaluator → save ThreadEvaluation row
6. Aggregate EvalRun saved (eval_type: batch_thread) with summary stats
7. Frontend polls completion → navigates to run detail
```

---

## Key Conventions

### API Contract: snake_case ↔ camelCase

Python code uses `snake_case` internally. API JSON uses `camelCase`. Translation is automatic via Pydantic's `CamelModel`/`CamelORMModel`:

```python
class EvalRunResponse(CamelORMModel):
    eval_type: str        # serializes as "evalType" in JSON
    created_at: datetime  # serializes as "createdAt" in JSON
```

### Versioned Resources

Prompts and schemas are versioned per `(app_id, type)`. The backend auto-increments version numbers when new rows are written. Always reference the latest version for a given type.

### Settings Scope

LLM settings are always global — stored at `app_id=""` (empty string, not `null`). Per-app settings use the actual app_id.

```
app_id=""         key="defaultProvider"   <- global LLM settings
app_id="voice-rx" key="language"          <- per-app non-LLM setting
```

Never pass an app_id when reading LLM settings. Fix callers, not the lookup function.

---

## Quick Reference

| Need to... | Use... |
|------------|--------|
| Make an HTTP request | `apiRequest`/`apiUpload` from `src/services/api/client.ts` |
| Access resource data | Repository wrappers in `src/services/api/*.ts` |
| Run a background evaluation | `submitAndPollJob()` from `src/services/api/jobPolling.ts` |
| Read/write UI state | Zustand stores in `src/stores/` — select slices |
| Navigate between pages | Route constants from `src/config/routes.ts` |
| Show user feedback | `notificationService.success/error/info/warning` |
| Log diagnostics | `logger` / `evaluationLogger` |
| Merge CSS classes | `cn()` from `src/utils/cn.ts` |
| Call an LLM | Provider wrappers in `backend/app/services/evaluators/llm_base.py` |
| Add a new evaluation type | Handler in `job_worker.py` + runner in `evaluators/` + frontend polling |
| Add a new API resource | Model + schema + route + frontend API module + store update |
