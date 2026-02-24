# AGENTS.md

Operational guide for agentic coding assistants in this repository.
Default to existing abstractions and local patterns; avoid unnecessary architecture churn.

## Rule precedence

1. Direct user instruction.
2. This file (`AGENTS.md`).
3. `.github/copilot-instructions.md` (when still aligned with live code).
4. Existing patterns in touched files.

## External rule files

- Copilot rules exist at `.github/copilot-instructions.md`.
- Cursor rules are currently absent (`.cursorrules` and `.cursor/rules/` not found).
- If external rules conflict with current code, follow current code plus this file.

## Current scheme of things (product + architecture)

- Active app IDs: `voice-rx`, `kaira-bot`.
- Do not reintroduce `kaira-evals` into frontend app settings/state.
- Platform workflow follows the 4-step scheme in `docs/guide/`: Bring Assets -> Review Setup -> Run Evaluators -> Run Full Evals.
- Voice Rx flow is a two-call pipeline: Call 1 transcription, then Call 2 critique (text-only JSON output).
- Kaira Bot supports custom evaluator runs, batch thread evaluations, and adversarial evaluations.
- Frontend stack: React 19, TypeScript strict, Vite 7, Tailwind v4, Zustand.
- Backend stack: FastAPI, async SQLAlchemy 2, asyncpg, Python 3.12.
- Database: PostgreSQL 16 with JSON/JSONB-heavy schema.
- API surface: 14 routers in `backend/app/main.py`.
- ORM surface: 15 tables from `backend/app/models/__init__.py`.
- Job worker entrypoint: `backend/app/services/job_worker.py`.
- Registered job types: `evaluate-voice-rx`, `evaluate-batch`, `evaluate-adversarial`, `evaluate-custom`, `evaluate-custom-batch`.

## docs/guide callout (keep guide and code aligned)

- `docs/guide/` is the interactive architecture/workflow reference.
- Edit source in `docs/guide/src/`; do not hand-edit generated `docs/guide/dist/`.
- Guide data is synced by `docs/guide/scripts/sync-data.ts`.
- If models/routes/workflows/template variables change, sync/update guide data too.
- Root-level guide command: `npm run dev:guide` (Docker guide profile).
- Guide package commands (`docs/guide/`): `npm run dev`, `npm run build`, `npm run preview`.

## Build, run, and lint commands

### Full stack (recommended for integration work)

- `docker compose up --build` or `npm run dev:stack`.
- `docker compose --profile guide up --build` or `npm run dev:guide`.
- `docker compose down`.
- `docker compose down -v` (stops services and wipes DB volume).
- `docker compose logs -f backend`.
- `docker compose logs -f frontend`.
- `docker compose logs -f guide`.

### Frontend (root project)

- `npm run dev` (Vite dev server on `:5173`).
- `npm run build` (`tsc -b && vite build`).
- `npm run lint` (ESLint across frontend code).
- `npx tsc -b` (typecheck only).
- Targeted lint: `npx eslint src/path/to/file.tsx`.

### Backend (local Python path)

- `pyenv activate venv-python-ai-evals-arize`.
- `pip install -r backend/requirements.txt`.
- `PYTHONPATH=backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8721`.

## Testing and single-test guidance

- Current state: no committed pytest/vitest/playwright config in this repo.
- Baseline validation is lint + typecheck + manual flows.
- For UI changes, validate desktop and mobile flows and inspect browser console/network.
- If introducing tests, prefer single-test runs:
  - Backend pytest: `python -m pytest backend/tests/test_file.py::test_name -q`
  - Vitest: `npx vitest run src/path/file.test.ts -t "test name"`
  - Playwright: `npx playwright test tests/path.spec.ts -g "scenario"`

## Frontend code style and conventions

### Imports, modules, naming

- Use `@/` alias for internal imports (`@` maps to `src`).
- Prefer `import type` for type-only imports.
- Keep import groups ordered: external packages, then internal `@/`.
- Reuse barrels where available (`src/services/api/index.ts`, `src/stores/index.ts`).
- Naming: PascalCase components, `useXxx` hooks, camelCase functions/variables.
- Prefer named exports for new feature files; keep existing default exports as-is.

### TypeScript, formatting, state

- Keep strict TypeScript guarantees; avoid `any` unless unavoidable and localized.
- Match local formatting (dominant style: single quotes + semicolons).
- Define explicit interfaces/types for API payloads and store state.
- Keep date parsing explicit at API boundaries (see `parseDates` patterns).
- In components, select Zustand slices (`useStore((s) => s.value)`), not full store objects.
- For one-off async reads/callbacks, use `useStore.getState()`.

### API access, errors, and user feedback

- Use `apiRequest` / `apiUpload` / `apiDownload` from `src/services/api/client.ts`.
- Use repository wrappers from `src/services/api/` and `src/services/storage/`.
- Avoid ad-hoc `fetch` directly in components.
- Use `src/config/routes.ts` constants/builders instead of hardcoded route strings.
- Normalize unknown errors with `err instanceof Error ? err.message : 'fallback'`.
- Route user-facing failures through `notificationService.error(...)`.
- Use `notificationService.success/info/warning` for user-visible feedback.
- Use `logger` / `evaluationLogger` for diagnostics; avoid production `console.log`.

### UI and styling

- Use Tailwind v4 and tokens from `src/styles/globals.css`.
- Prefer CSS variables (`var(--text-primary)`, `var(--bg-secondary)`) over hardcoded colors.
- Use `cn()` from `src/utils/cn.ts` for class merging.
- Reuse primitives in `src/components/ui/` before introducing new variants.

## Backend code style and conventions

### API and schema contracts

- Keep Python internals in snake_case; API JSON is camelCase via `CamelModel`/`CamelORMModel`.
- Schema naming convention: `XxxCreate`, `XxxUpdate`, `XxxResponse`.
- Use async sessions via `Depends(get_db)` and SQLAlchemy `select()` patterns.
- Raise `HTTPException` with stable `detail` messages for client-facing failures.

### Data model and evaluator invariants

- `EvalRun` is the unified record for evaluation outcomes.
- Preserve `eval_type` polymorphism (`custom`, `full_evaluation`, `human`, `batch_thread`, `batch_adversarial`).
- Preserve FK/cascade chain (`listings`/`chat_sessions` -> `eval_runs` -> thread/adversarial/api logs).
- Keep prompt/schema versioning app-scoped when writing new rows.
- Voice Rx invariant: transcription first, critique second, critique uses text-only `generate_json`.
- Compute summaries/statistics server-side from known records, not LLM self-reports.

### Worker, providers, and safety

- Preserve cooperative cancellation checks (`is_job_cancelled()`) in long-running flows.
- Preserve progress updates (`update_job_progress`) and startup stale-job recovery paths.
- Keep LLM usage behind provider wrappers in `backend/app/services/evaluators/llm_base.py`.
- Do not call OpenAI/Gemini SDKs directly from evaluator runner implementations.

## Common pitfalls

- Most backend list/get endpoints require `app_id`; do not omit it.
- `settings` API uses empty string `''` for global scope (not `null`).
- Respect listing `source_type` rules; do not mix upload and API-flow data.
- Prefer `submitAndPollJob(...)` over custom component-level polling loops.
- If model shapes change, update models + schemas + seed defaults + affected routes together.
- For local Python scripts/tools, use `pyenv activate venv-python-ai-evals-arize`.
- Kaira/MyTatva default user id remains `c22a5505-f514-11f0-9722-000d3a3e18d5`.
- When architecture/workflow changes, update both code and `docs/guide/` documentation.
