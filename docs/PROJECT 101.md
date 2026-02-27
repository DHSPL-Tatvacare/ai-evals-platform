# AI Evals Platform - Project 101

A guided walkthrough of how this codebase works, aimed at new developers and coding agents. Follows a real user flow to explain how all the layers connect.

---

## Architecture Overview

This is a full-stack application with a clear separation between frontend and backend:

```
Browser (React)                     Server (FastAPI)                  Database
┌───────────────────┐   HTTP/JSON   ┌──────────────────────┐         ┌──────────┐
│  UI Components    │──────────────>│  API Routers (15)    │────────>│          │
│  Zustand Stores   │<──────────────│  Services/Evaluators │<────────│ Postgres │
│  API Client Layer │               │  Job Worker          │         │  (JSONB) │
└───────────────────┘               │  LLM Providers       │         └──────────┘
     :5173                          └──────────────────────┘
                                         :8721
```

**Key principle:** The frontend never calls LLM APIs directly. All evaluation logic, LLM calls, and data persistence run through the FastAPI backend. The frontend is a thin client that manages UI state and makes API calls.

---

## The Two Workspaces

The platform has two active app IDs, each with their own evaluation workflows:

### Voice Rx (`voice-rx`)
Medical transcription evaluation. Users upload audio files and reference transcripts, then run a two-call evaluation pipeline:
1. **Transcription call** - LLM listens to audio and generates a transcript
2. **Critique call** - LLM compares the generated transcript against the reference (text-only, no audio)

### Kaira Bot (`kaira-bot`)
Conversational AI evaluation. Users chat with a bot, then run evaluators against the conversation data. Supports:
- Single custom evaluator runs
- Batch thread evaluations (from CSV)
- Adversarial testing (automated red-teaming)

---

## Frontend Layer (`src/`)

### Folder Responsibilities

```
src/
├── components/ui/       <- Generic UI primitives (Button, Modal, Card, Badge)
├── config/              <- Route constants, app configuration
├── constants/           <- Hardcoded values, default configs
├── features/            <- Domain-specific modules (see below)
├── hooks/               <- Reusable React logic
├── services/
│   ├── api/             <- HTTP client + per-resource API modules
│   ├── storage/         <- Barrel re-export from api/ (backward compat)
│   ├── notifications/   <- Toast messages
│   └── logger/          <- Structured diagnostic logging
├── stores/              <- Zustand state management (13 stores)
├── styles/              <- Tailwind v4 globals + CSS variables
├── types/               <- TypeScript interfaces and type definitions
└── utils/               <- Pure helper functions (cn, date parsing, etc.)
```

### Feature Modules (`src/features/`)

Each feature is a self-contained domain module with its own components, hooks, and utils:

| Feature | Purpose |
|---------|---------|
| `voiceRx` | Dashboard, run list, run detail, settings for voice-rx evaluations |
| `evalRuns` | Shared evaluation dashboard, run list, run detail (used by kaira-bot) |
| `kaira` | Chat interface, message tagging, trace analysis, action buttons |
| `kairaBotSettings` | Kaira-specific settings and tag management |
| `settings` | Shared settings infrastructure (LLM provider config, prompt/schema editors) |
| `upload` | File upload with drag-and-drop, CSV preview, validation |
| `transcript` | Transcript viewer with segment-level display and audio alignment |
| `structured-outputs` | JSON viewer, schema validator, structured output display |
| `evals` | Metric displays, comparison cards, evaluation statistics |
| `export` | PDF/CSV/JSON export with format selectors |
| `listings` | Listing cards, list views, detail views |
| `common` | Shared feature components (35+ UI primitives) |

### Zustand Stores (`src/stores/`)

Stores are in-memory caches of server data plus ephemeral UI state. They follow a consistent pattern:

```typescript
// Pattern: Store calls API repository, caches result, React re-renders
export const usePromptsStore = create<PromptsState>((set, get) => ({
  prompts: { 'voice-rx': [], 'kaira-bot': [] },

  loadPrompts: async (appId) => {
    const prompts = await promptsApi.getAll(appId);
    set((state) => ({
      prompts: { ...state.prompts, [appId]: prompts },
    }));
  },
}));
```

**13 stores:** `appStore`, `appSettingsStore`, `llmSettingsStore`, `globalSettingsStore`, `listingsStore`, `schemasStore`, `promptsStore`, `evaluatorsStore`, `chatStore`, `uiStore`, `miniPlayerStore`, `taskQueueStore`, `jobTrackerStore`.

**Critical pattern:** Always select slices in components, never the full store:
```typescript
// Good - re-renders only when prompts change
const prompts = usePromptsStore((s) => s.prompts['voice-rx']);

// Bad - re-renders on ANY store change
const store = usePromptsStore();
```

### API Client Layer (`src/services/api/`)

All HTTP communication goes through a shared client with typed repository wrappers:

| Module | Purpose |
|--------|---------|
| `client.ts` | Shared HTTP client (`apiRequest`, `apiUpload`, `apiDownload`) |
| `listingsApi.ts` | Listing CRUD |
| `filesApi.ts` | File upload/download |
| `promptsApi.ts` | Versioned prompts |
| `schemasApi.ts` | Versioned schemas |
| `evaluatorsApi.ts` | Custom evaluator definitions |
| `evalRunsApi.ts` | Evaluation run results |
| `chatApi.ts` | Chat sessions and messages |
| `jobsApi.ts` | Job status polling |
| `jobPolling.ts` | `submitAndPollJob()` - async job lifecycle abstraction |
| `settingsApi.ts` | Settings persistence |
| `tagsApi.ts` | Tag management |
| `adversarialConfigApi.ts` | Adversarial test configuration |
| `historyApi.ts` | Activity history |

### Frontend Routes (`src/config/routes.ts`)

**Voice Rx:**
- `/upload` - Upload audio/transcript files
- `/listing/:id` - Individual listing detail
- `/dashboard` - Evaluation dashboard with metrics
- `/runs` - Run list with filtering
- `/runs/:runId` - Individual run detail
- `/logs` - API call logs
- `/settings` - Voice Rx settings (prompts, schemas, LLM config)

**Kaira Bot:**
- `/kaira/chat` - Chat interface
- `/kaira/dashboard` - Evaluation dashboard
- `/kaira/runs` - Run list
- `/kaira/runs/:runId` - Run detail
- `/kaira/runs/:runId/adversarial/:evalId` - Adversarial case detail
- `/kaira/threads/:threadId` - Thread detail
- `/kaira/logs` - API call logs
- `/kaira/settings` - Kaira settings
- `/kaira/settings/tags` - Tag management

---

## Backend Layer (`backend/`)

### Structure

```
backend/
├── app/
│   ├── main.py              <- FastAPI app, router registration, lifespan
│   ├── database.py          <- Async SQLAlchemy engine + session factory
│   ├── models/              <- 15 ORM models (SQLAlchemy 2 Mapped[] style)
│   ├── schemas/             <- Pydantic request/response schemas (CamelModel)
│   ├── routes/              <- 15 API routers
│   └── services/
│       ├── evaluators/      <- LLM providers, evaluation runners
│       ├── job_worker.py    <- Background job dispatch + handler registry
│       ├── seed_defaults.py <- Startup seeding (prompts, schemas, evaluators)
│       └── evaluation_constants.py <- System prompts, normalization templates
├── requirements.txt
└── Dockerfile
```

### Database Models (15 tables)

```
Listing ──────────┐
                  ├──> EvalRun ──┬──> ThreadEvaluation
ChatSession ──────┘     │        ├──> AdversarialEvaluation
    │                   │        └──> ApiLog
    └──> ChatMessage    │
                        └──> Job
                        └──> Evaluator (nullable FK)

Standalone:
  Prompt, Schema, FileRecord, History, Setting, Tag
```

**Core entity: `EvalRun`** - Unified record for all evaluation outcomes. The `eval_type` field determines the polymorphic shape:
- `full_evaluation` - Voice Rx two-call pipeline result
- `custom` - Single custom evaluator output
- `human` - Manual review/annotation
- `batch_thread` - Kaira batch thread evaluation
- `batch_adversarial` - Kaira adversarial test result

### API Routers (15)

| Router | Prefix | Purpose |
|--------|--------|---------|
| `listings` | `/api/listings` | Evaluation source data (audio, transcripts) |
| `files` | `/api/files` | File upload/download/metadata |
| `prompts` | `/api/prompts` | Versioned LLM prompts (per-app, per-type) |
| `schemas` | `/api/schemas` | JSON schemas for structured output |
| `evaluators` | `/api/evaluators` | Custom evaluator definitions |
| `chat` | `/api/chat` | Chat sessions and messages (Kaira) |
| `history` | `/api/history` | Activity history tracking |
| `settings` | `/api/settings` | Global and per-app settings |
| `tags` | `/api/tags` | Message classification tags |
| `jobs` | `/api/jobs` | Background job queue and polling |
| `eval_runs` | `/api/eval-runs` | Evaluation results (all types) |
| `threads` | `/api/threads` | Thread-level evaluation aggregation |
| `llm` | `/api/llm` | LLM provider config and testing |
| `adversarial_config` | `/api/adversarial` | Adversarial test case management |
| `admin` | `/api/admin` | Administrative operations |

### Job Worker (`backend/app/services/job_worker.py`)

Long-running evaluations execute as background jobs. The worker uses a handler registry pattern:

```python
@register_job_handler("evaluate-voice-rx")
async def handle_voice_rx(job, session):
    # Transcription call -> Critique call -> Save results
    ...
```

**5 registered handlers:**
1. `evaluate-voice-rx` - Voice Rx two-call pipeline
2. `evaluate-batch` - Batch thread evaluation from CSV
3. `evaluate-adversarial` - Adversarial test execution
4. `evaluate-custom` - Single custom evaluator
5. `evaluate-custom-batch` - Batch custom evaluator

**Safety features:**
- Cooperative cancellation via `is_job_cancelled()` checks
- Progress tracking via `update_job_progress()`
- Stale job recovery on startup (jobs stuck >15 minutes)
- Orphaned eval_run reconciliation

### LLM Providers (`backend/app/services/evaluators/llm_base.py`)

All LLM calls go through a provider abstraction. Never call SDKs directly from runners.

**Gemini (primary):**
- Service account auth (Vertex AI) for backend jobs - reliable for long tasks
- API key auth (Developer API) for frontend-triggered settings generation
- Model family detection: 2.0, 2.5, 3.0, 3.1
- Thinking config: `thinking_budget` (int) for 2.5, `thinking_level` (enum) for 3+
- Vertex AI uses `Part.from_bytes()` for media (no file upload API)

**OpenAI (secondary):**
- API key auth
- Async wrapper via `asyncio.to_thread()`

**Timeout tiers:**
| Tier | Timeout | Use case |
|------|---------|----------|
| `text_only` | 60s | Text-only generation |
| `with_schema` | 90s | Structured JSON output |
| `with_audio` | 180s | Audio transcription |
| `with_audio_and_schema` | 240s | Audio + structured output |

### Evaluation Runners

| Runner | File | Purpose |
|--------|------|---------|
| Voice Rx Runner | `voice_rx_runner.py` | Two-call transcription + critique pipeline |
| Custom Runner | `custom_evaluator_runner.py` | Execute user-defined evaluator prompt + schema |
| Batch Runner | `batch_runner.py` | CSV-based batch processing for threads and adversarial |
| Intent Evaluator | `intent_evaluator.py` | Intent classification |
| Correctness Evaluator | `correctness_evaluator.py` | Correctness assessment |
| Efficiency Evaluator | `efficiency_evaluator.py` | Efficiency/workflow evaluation |
| Adversarial Evaluator | `adversarial_evaluator.py` | Adversarial test case execution |

### Seed Defaults (`backend/app/services/seed_defaults.py`)

On startup, the backend seeds default prompts, schemas, and evaluators for both apps:

**Voice Rx seeds:** 5 prompts (transcription/evaluation/extraction for upload and API flows), 3 schemas (transcription segments, evaluation critique, API format), 3 evaluators (Intent, Correctness, Efficiency)

**Kaira Bot seeds:** 2 prompts (system prompt, conversation starter), 1 schema (chat format), 3 evaluators (Intent, Correctness, Efficiency)

---

## Data Flow: End-to-End Example

### Use Case: Voice Rx Full Evaluation

**User uploads an audio file and runs a full evaluation.**

```
1. UPLOAD
   Browser                      Backend
   FileDropZone component       POST /api/files (multipart upload)
       │                            │
       └─> filesApi.upload()        └─> FileRecord saved to DB
                                        file written to uploads/

2. CREATE LISTING
   ListingCard component        POST /api/listings
       │                            │
       └─> listingsApi.create()     └─> Listing row with file references

3. RUN EVALUATION
   RunAllOverlay component      POST /api/jobs
       │                            │
       └─> submitAndPollJob()       └─> Job row created (status: queued)
           │                            │
           │  polls GET /api/jobs/:id   │  job_worker picks up job
           │  every few seconds         │
           │                            ├─> Call 1: Transcription
           │                            │   GeminiProvider.generate() with audio
           │                            │   System prompt: multilingual, script-aware
           │                            │
           │                            ├─> Call 2: Critique (text-only)
           │                            │   GeminiProvider.generate_json()
           │                            │   Compares AI transcript vs reference
           │                            │
           │                            ├─> EvalRun saved (eval_type: full_evaluation)
           │                            ├─> ApiLog entries saved (both LLM calls)
           │                            └─> Job status: completed
           │
           └─> navigates to /runs/:runId

4. VIEW RESULTS
   VoiceRxRunDetail page        GET /api/eval-runs/:id
       │                            │
       └─> evalRunsApi.getById()    └─> Returns EvalRun with result JSON
                                        segment-level findings, aggregate stats
```

### Use Case: Kaira Batch Thread Evaluation

```
1. User uploads thread CSV data via upload interface
2. Frontend calls submitAndPollJob("evaluate-batch", { csv data })
3. Backend job_worker dispatches to batch_runner
4. batch_runner iterates rows, runs evaluators per thread
5. Per-thread results saved as ThreadEvaluation rows
6. Aggregate EvalRun record saved with summary stats
7. Frontend polls completion, navigates to run detail
```

---

## Key Conventions

### API Contract: snake_case <-> camelCase

Python code uses `snake_case` internally. API JSON uses `camelCase`. The translation is automatic via Pydantic's `CamelModel`:

```python
# Backend model (snake_case)
class EvalRunResponse(CamelORMModel):
    eval_type: str        # -> "evalType" in JSON
    created_at: datetime  # -> "createdAt" in JSON
```

### Versioned Resources

Prompts and schemas are versioned per (app_id, type). The backend auto-increments version numbers:

```
prompt: app_id="voice-rx", prompt_type="transcription", version=1
prompt: app_id="voice-rx", prompt_type="transcription", version=2  <- newer
```

### Settings Scope

Settings can be global or per-app. Global scope uses empty string `''` as app_id (not `null`):

```
setting: app_id="",          key="defaultProvider"    <- global
setting: app_id="voice-rx",  key="language"           <- per-app
```

---

## Mental Models

### 1. Frontend is a Thin Client
All business logic lives in the backend. The frontend manages UI state, makes API calls, and renders results. It never calls LLM APIs directly.

### 2. EvalRun is the Central Entity
Every evaluation outcome - whether from Voice Rx, custom evaluators, batch threads, or adversarial tests - is an `EvalRun` record. The `eval_type` field determines the shape and meaning of the `result` JSON.

### 3. Jobs are the Execution Model
Any operation that takes more than a few seconds runs as a background job. The pattern is always: create job -> poll status -> get result. Use `submitAndPollJob()`, not custom polling loops.

### 4. Stores are Caches, Not Sources of Truth
Zustand stores cache data fetched from the API. On page load, stores call their `load*()` methods to fetch fresh data. The PostgreSQL database is the single source of truth.

### 5. Provider Abstraction Protects Runners
Evaluation runners never call Gemini/OpenAI SDKs directly. They go through `llm_base.py` providers, which handle auth, retries, timeouts, and token tracking uniformly.

---

## Quick Reference

| Need to... | Use... |
|------------|--------|
| Make an API call | `apiRequest`/`apiUpload` from `src/services/api/client.ts` |
| Access resource data | Repository wrappers in `src/services/api/*.ts` |
| Run a background evaluation | `submitAndPollJob()` from `src/services/api/jobPolling.ts` |
| Read/write global state | Zustand stores in `src/stores/` (select slices) |
| Navigate between pages | Route constants from `src/config/routes.ts` |
| Show user feedback | `notificationService.success/error/info/warning` |
| Log diagnostics | `logger`/`evaluationLogger` (not `console.log`) |
| Merge CSS classes | `cn()` from `src/utils/cn.ts` |
| Define data shapes | Interfaces in `src/types/` |
| Add a new evaluation type | Add handler in `job_worker.py`, runner in `evaluators/`, frontend polling |
| Add a new API resource | Model + schema + route + frontend API module + store |
