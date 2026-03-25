# Job Queue — Complete Flow Map (All Callsites)

## Flow 1: Batch Evaluation (evaluate-batch)

```
NewBatchEvalOverlay.tsx
  │ handleSubmit()
  ▼
useSubmitAndRedirect.ts
  │ jobsApi.submit('evaluate-batch', params)  ← NO api_key in params
  │ jobTrackerStore.trackJob(...)
  │ Brief poll (10s max) for run_id
  ▼
Redirect to RunDetail
  │ Polling: jobsApi.get(jobId) in usePoll
  │ Cancel: jobsApi.cancel(jobId)
  ▼
JobCompletionWatcher (global)
  │ Polls tracked jobs every 5s
  │ Toasts on terminal state
  │ Untrack on terminal
```

**Backend flow:**
```
worker_loop → pick queued → status=running
  → handle_evaluate_batch()
    → get_llm_settings_from_db(provider_override=...)  ← uses DB for api_key
    → run_batch_evaluation()
      → parallel thread workers (asyncio.Semaphore)
      → update_job_progress() per thread
      → is_job_cancelled() per thread
    → status=completed (or failed/cancelled)
```

**Queue messaging:** User redirected to RunDetail immediately. Sees progress bar.
**Gap:** No "queued" indicator if job waits in queue. User sees stale detail page.

---

## Flow 2: Adversarial Evaluation (evaluate-adversarial)

```
NewAdversarialOverlay.tsx
  │ handleSubmit()
  ▼
useSubmitAndRedirect.ts  ← SAME pattern as batch
  │ jobsApi.submit('evaluate-adversarial', params)
  │ jobTrackerStore.trackJob(...)
  │ Brief poll → Redirect
  ▼
RunDetail + JobCompletionWatcher (same as batch)
```

**Backend flow:** Same pattern as batch. Uses case_workers for parallelism within job.
**Gap:** Same — no queued indicator.

---

## Flow 3: Voice-RX Evaluation (evaluate-voice-rx)

```
EvaluationOverlay.tsx / EvaluatorsView.tsx
  │ useUnifiedEvaluation or useAIEvaluation hook
  ▼
submitAndPollJob('evaluate-voice-rx', params)
  │ Polls in-component until terminal
  │ onProgress → updates task queue
  │ onJobCreated → trackJob
  ▼
Component shows inline progress/result
```

**Queue messaging:** Component shows progress. But "queued" state shows as initial spinner.
**Gap:** No explicit "queued" message.

---

## Flow 4: Custom Evaluation (evaluate-custom / evaluate-custom-batch)

```
EvaluatorsView.tsx / KairaBotEvaluatorsView.tsx
  │ useEvaluatorRunner → evaluatorExecutor.execute()
  ▼
submitAndPollJob('evaluate-custom', params)
  │ Polls until terminal
  │ Returns EvalRun
  ▼
Updates evaluator card with result
```

**Queue messaging:** Shows spinner on evaluator card.
**Gap:** No "queued" vs "running" distinction.

---

## Flow 5: Report Generation (generate-report)

```
ReportTab.tsx
  │ generateReport(refresh?)
  ▼
jobsApi.submit('generate-report', {
  run_id, refresh, provider, model  ← NO api_key
})
  │ pollAndLoad(jobId, isRefresh)
  │   → pollJobUntilComplete(jobId, ...)
  │   → On complete: reportsApi.fetchReport(runId, cacheOnly)
  ▼
Shows report content
```

**Backend flow:**
```
worker_loop → pick queued → status=running
  → handle_generate_report()
    → ReportService.generate(run_id, provider, model)
      → aggregate data (no LLM)
      → _generate_narrative()
        → get_llm_settings_from_db(provider_override=provider)
        → create_llm_provider(provider, api_key, model)
        → provider.generate(narrative_prompt)
      → cache in evaluation_analytics
    → status=completed
```

**Queue messaging:** Shows "Generating report..." with progress message.
**Gaps:**
1. NO "queued" state shown — jumps to "generating" immediately
2. `pollAndLoad` missing `cancelled` handler → UI stuck in generating state
3. Silent Anthropic failure in _generate_narrative fallback
4. No api_key passed in params — relies solely on DB lookup

---

## Flow 6: Cross-Run Report (generate-cross-run-report)

```
IssuesTab.tsx
  │ handleGenerate()
  ▼
reportsApi.generateCrossRunSummary(payload)  ← DIRECT API CALL, NOT A JOB
  │ POST /api/reports/cross-run-analytics/refresh
  ▼
Shows summary inline
```

**Backend flow:**
```
POST /api/reports/cross-run-analytics/refresh
  → Creates job: 'generate-cross-run-report'
  → Polls job internally? OR returns immediately?
  → Actually: reads code...
```

Wait — need to verify. The IssuesTab calls reportsApi which creates a JOB,
but the frontend doesn't poll it as a job.

**NEED TO CHECK:** Does the refresh endpoint create a job and return cached?
Or does it block until the job completes? → CHECK backend/app/routes/reports.py

---

## Global State Machine (Target)

```
                    ┌─────────┐
                    │ SUBMIT  │ Frontend sends POST /api/jobs
                    └────┬────┘
                         ▼
                    ┌─────────┐
           ┌───────│ QUEUED  │ DB row created, status=queued
           │       └────┬────┘
           │            │      Worker picks up (was blocked)
           │            ▼
           │       ┌─────────┐
           │       │ RUNNING │ status=running, started_at set
           │       └────┬────┘
           │            │
     Cancel│    ┌───────┼───────┐
           │    ▼       ▼       ▼
           │ ┌─────┐ ┌──────┐ ┌──────────┐
           └→│CANCL│ │COMPL │ │ FAILED   │
             └─────┘ └──────┘ └──────────┘
```

## Frontend Notification Gaps

| Transition | Current Behavior | Needed |
|------------|-----------------|--------|
| Submitted → Queued | Redirect (batch/adv) or "Generating..." (report) | "Job queued" toast |
| Queued → Running | No notification | "Job started" toast or status update |
| Running → Completed | Toast from JobCompletionWatcher | OK (keep) |
| Running → Failed | Toast from JobCompletionWatcher | OK (keep) |
| Running → Cancelled | Toast from JobCompletionWatcher | OK (keep) |
| Queued → Cancelled | Not handled in pollAndLoad | Need cancelled handler |
