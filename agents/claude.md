# Claude Agent Guide

Claude agents working in this repository should treat `AGENTS.md` as the primary source of truth.
This file is a quick companion with Claude-specific emphasis.

## Precedence

1. Direct user instruction
2. `AGENTS.md`
3. `.github/copilot-instructions.md`
4. Existing code patterns in touched files

## External rule files

- Copilot rules exist at `.github/copilot-instructions.md`.
- Cursor rules are currently absent (`.cursorrules` and `.cursor/rules/` not found).

## Current scheme of things

- Active app IDs: `voice-rx`, `kaira-bot`.
- Do not reintroduce `kaira-evals` in frontend app-state/settings.
- Product workflow follows the 4-step model:
  1. Bring Assets
  2. Review Setup
  3. Run Evaluators
  4. Run Full Evals
- Voice Rx is a two-call flow: transcription, then critique.
- Kaira Bot supports custom evaluator runs, batch thread evals, and adversarial evals.

## docs/guide alignment

- Treat `docs/guide/` as the architecture/workflow reference.
- Edit only `docs/guide/src/`; never hand-edit generated `docs/guide/dist/`.
- Run sync via `docs/guide/scripts/sync-data.ts` (wired into guide dev/build scripts).
- If routes/models/workflows/template vars change, update guide data too.

## Command quick reference

- Full stack: `docker compose up --build` or `npm run dev:stack`
- Full stack + guide: `npm run dev:guide`
- Frontend lint: `npm run lint`
- Frontend typecheck: `npx tsc -b`
- Frontend targeted lint: `npx eslint src/path/to/file.tsx`
- Backend local run:
  - `pyenv activate venv-python-ai-evals-arize`
  - `PYTHONPATH=backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8721`

## Style reminders

- Frontend imports: external first, then `@/`; prefer `import type` for type-only imports.
- TS style: strict types, avoid broad `any`, match local formatting.
- API calls: use repository wrappers and `apiRequest`/`apiUpload`/`apiDownload`.
- Error handling: normalize unknown errors and surface user-facing errors via `notificationService`.
- Logging: use `logger`/`evaluationLogger`; avoid ad-hoc production `console.log`.
- Backend API JSON should remain camelCase through `CamelModel`/`CamelORMModel`.

## Key invariants

- Preserve `EvalRun` as the unified evaluation outcome record.
- Preserve job cancellation/progress patterns in `job_worker.py`.
- Keep Voice Rx critique text-only (`generate_json`) after transcription.
- Most list/get backend endpoints require `app_id`.
- `settings` global scope uses empty string `''` for `app_id`.
- Keep docs and implementation in sync whenever architecture changes.
