# Frontend Changes

## New Component: `ParallelConfigSection.tsx`

Reusable component with:
- Toggle switch (on/off)
- Slider (2–10 workers, shown only when toggle is on)
- Styled to match `ReviewStep` sections (same border, bg, spacing)

Props: `parallel`, `workers`, `onParallelChange`, `onWorkersChange`, `label`, `description`

## NewBatchEvalOverlay.tsx

- Added state: `parallelThreads` (bool, default false), `threadWorkers` (number, default 3)
- Review step (step 5) renders `<ParallelConfigSection>` below `<ReviewStep>`
- Review sections include a "Parallelism" row showing "Sequential" or "Yes (N workers)"
- Submit handler sends `parallel_threads` and `thread_workers` to backend
- Removed: `parallelCustomEvals` state, its submit param, its prop to EvaluatorToggleStep

## NewAdversarialOverlay.tsx

- Added state: `parallelCases` (bool, default false), `caseWorkers` (number, default 3)
- Review step (step 4) renders `<ParallelConfigSection>` below `<ReviewStep>`
- Review sections include a "Parallelism" row
- Submit handler sends `parallel_cases` and `case_workers` to backend

## EvaluatorToggleStep.tsx

- Removed from interface: `parallelCustomEvals`, `onParallelCustomEvalsChange`
- Removed from destructuring: same two props
- Removed: the "Run custom evaluators in parallel" checkbox UI block

## job_worker.py (Backend Wiring)

- `handle_evaluate_batch`: passes `parallel_threads`, `thread_workers` from `params`
- `handle_evaluate_adversarial`: passes `parallel_cases`, `case_workers` from `params`
- Removed: `parallel_custom_evals` param pass-through
