# Phase 2: Seed Evaluators + UX

**Goal:** Define 10 seed evaluator constants (5 upload, 5 API), add a backend endpoint to create them on listings, add fail-fast for unresolved variables, and add "Add recommended" UX in the frontend.
**Risk Level:** Medium — new endpoint, new UI element, prompt design, variable resolution validation.
**Prerequisite:** Phase 1 must be completed first (variables cleaned up, dynamic path extraction expanded).

---

## 1. Seed Evaluator Definitions

**File:** `backend/app/services/seed_defaults.py`

Add two new constants: `VOICE_RX_UPLOAD_EVALUATORS` and `VOICE_RX_API_EVALUATORS`. These are NOT seeded to the DB on startup — they live as code constants referenced by the seed-defaults endpoint.

### Shared Output Schemas

All 5 metrics have identical output schemas across both flow variants. Only the prompts differ.

#### 1. Medical Entity Recall (MER)

```python
{
    "name": "Medical Entity Recall",
    "output_schema": [
        {
            "key": "entity_recall_pct",
            "type": "number",
            "description": "Percentage of clinical entities from the audio captured in the output (0-100)",
            "displayMode": "header",
            "isMainMetric": True,
            "thresholds": {"green": 90, "yellow": 70},
        },
        {
            "key": "total_entities",
            "type": "number",
            "description": "Total distinct clinical entities identified in the audio",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "entities_captured",
            "type": "number",
            "description": "Number of entities successfully captured in the output",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "missed_entities",
            "type": "array",
            "description": "List of entities present in audio but missing from output",
            "displayMode": "card",
            "isMainMetric": False,
            "arrayItemSchema": {
                "itemType": "object",
                "properties": [
                    {"key": "entity", "type": "string", "description": "The missed entity"},
                    {"key": "category", "type": "string", "description": "Entity category (diagnosis, medication, symptom, history, vital, allergy)"},
                    {"key": "severity", "type": "string", "description": "Impact of omission (critical, moderate, minor)"},
                ],
            },
        },
        {
            "key": "reasoning",
            "type": "text",
            "description": "Methodology and key findings summary",
            "displayMode": "hidden",
            "isMainMetric": False,
            "role": "reasoning",
        },
    ],
}
```

#### 2. Factual Integrity

```python
{
    "name": "Factual Integrity",
    "output_schema": [
        {
            "key": "factual_accuracy_pct",
            "type": "number",
            "description": "Percentage of extracted data points that are factually supported by the source (0-100)",
            "displayMode": "header",
            "isMainMetric": True,
            "thresholds": {"green": 95, "yellow": 85},
        },
        {
            "key": "total_claims",
            "type": "number",
            "description": "Total data points/claims checked in the output",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "unsupported_count",
            "type": "number",
            "description": "Number of claims not supported by the source",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "unsupported_claims",
            "type": "array",
            "description": "List of data points in the output that cannot be traced to the source",
            "displayMode": "card",
            "isMainMetric": False,
            "arrayItemSchema": {
                "itemType": "object",
                "properties": [
                    {"key": "claim", "type": "string", "description": "The unsupported claim/data point"},
                    {"key": "issue", "type": "string", "description": "Why this is unsupported (fabricated, inferred, misquoted)"},
                ],
            },
        },
        {
            "key": "reasoning",
            "type": "text",
            "description": "Assessment methodology and key findings",
            "displayMode": "hidden",
            "isMainMetric": False,
            "role": "reasoning",
        },
    ],
}
```

#### 3. Negation Consistency

```python
{
    "name": "Negation Consistency",
    "output_schema": [
        {
            "key": "negation_accuracy_pct",
            "type": "number",
            "description": "Percentage of negated/denied conditions correctly mapped in output (0-100)",
            "displayMode": "header",
            "isMainMetric": True,
            "thresholds": {"green": 95, "yellow": 80},
        },
        {
            "key": "total_negations",
            "type": "number",
            "description": "Total negated/denied/excluded conditions found in source",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "correct_negations",
            "type": "number",
            "description": "Number of negations correctly represented in output",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "errors",
            "type": "array",
            "description": "List of negation errors",
            "displayMode": "card",
            "isMainMetric": False,
            "arrayItemSchema": {
                "itemType": "object",
                "properties": [
                    {"key": "entity", "type": "string", "description": "The condition/entity"},
                    {"key": "source_says", "type": "string", "description": "What the source says (e.g., 'denied', 'stopped taking')"},
                    {"key": "output_says", "type": "string", "description": "How the output represents it (e.g., 'active diagnosis', 'current medication')"},
                ],
            },
        },
        {
            "key": "reasoning",
            "type": "text",
            "description": "Assessment methodology and key findings",
            "displayMode": "hidden",
            "isMainMetric": False,
            "role": "reasoning",
        },
    ],
}
```

#### 4. Temporal Precision

```python
{
    "name": "Temporal Precision",
    "output_schema": [
        {
            "key": "temporal_accuracy_pct",
            "type": "number",
            "description": "Percentage of temporal references correctly linked to their entities (0-100)",
            "displayMode": "header",
            "isMainMetric": True,
            "thresholds": {"green": 90, "yellow": 75},
        },
        {
            "key": "total_temporal_refs",
            "type": "number",
            "description": "Total temporal references found in source (durations, frequencies, dates, timelines)",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "correct_refs",
            "type": "number",
            "description": "Number of temporal references correctly captured in output",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "errors",
            "type": "array",
            "description": "List of temporal precision errors",
            "displayMode": "card",
            "isMainMetric": False,
            "arrayItemSchema": {
                "itemType": "object",
                "properties": [
                    {"key": "entity", "type": "string", "description": "The clinical entity with temporal context"},
                    {"key": "source_timing", "type": "string", "description": "Timing as stated in the source"},
                    {"key": "output_timing", "type": "string", "description": "Timing as captured in the output (or 'missing')"},
                ],
            },
        },
        {
            "key": "reasoning",
            "type": "text",
            "description": "Assessment methodology and key findings",
            "displayMode": "hidden",
            "isMainMetric": False,
            "role": "reasoning",
        },
    ],
}
```

#### 5. Critical Safety Audit

```python
{
    "name": "Critical Safety Audit",
    "output_schema": [
        {
            "key": "safety_pass",
            "type": "boolean",
            "description": "Whether ALL critical red-flag symptoms from the audio were captured in the output",
            "displayMode": "header",
            "isMainMetric": True,
        },
        {
            "key": "red_flags_in_source",
            "type": "number",
            "description": "Total critical/life-threatening symptoms identified in the audio",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "red_flags_captured",
            "type": "number",
            "description": "Number of red flags successfully captured in the output",
            "displayMode": "card",
            "isMainMetric": False,
        },
        {
            "key": "missed_red_flags",
            "type": "array",
            "description": "Critical symptoms present in audio but missing from output",
            "displayMode": "card",
            "isMainMetric": False,
            "arrayItemSchema": {
                "itemType": "object",
                "properties": [
                    {"key": "symptom", "type": "string", "description": "The missed red-flag symptom"},
                    {"key": "context", "type": "string", "description": "Context from the audio (e.g., 'patient reports chest pain radiating to left arm')"},
                ],
            },
        },
        {
            "key": "reasoning",
            "type": "text",
            "description": "Assessment methodology and key findings",
            "displayMode": "hidden",
            "isMainMetric": False,
            "role": "reasoning",
        },
    ],
}
```

### Prompt Design

Each metric has two prompt variants. The upload variant uses `{{audio}}` + `{{transcript}}`. The API variant uses `{{audio}}` + `{{input}}` + `{{rx}}`.

**Prompt structure** (same across all 5, with metric-specific instructions):

```
Upload variant:
- System context: "You are a medical documentation quality auditor."
- Input section: {{audio}} and {{transcript}}
- Task: Compare audio against transcript for [metric-specific criteria]
- Output format: Describe each output_schema field and what it should contain

API variant:
- System context: "You are a medical documentation quality auditor."
- Input section: {{audio}}, {{input}} (transcript), and {{rx}} (structured extraction)
- Task: Compare audio+transcript against structured extraction for [metric-specific criteria]
- Output format: Same as upload (identical output_schema)
```

The full prompt text for all 10 evaluators should be written during implementation. Each prompt should:
1. Clearly describe the evaluator's role
2. Explain what the input data represents
3. Define the clinical entity categories to check
4. Explain the scoring methodology
5. Reference each output schema field by name with instructions

### Constant Structure

```python
# In seed_defaults.py:

VOICE_RX_UPLOAD_EVALUATORS = [
    {
        "name": "Medical Entity Recall",
        "prompt": "...",  # Uses {{audio}} + {{transcript}}
        "output_schema": [...],  # Shared schema from above
    },
    # ... 4 more
]

VOICE_RX_API_EVALUATORS = [
    {
        "name": "Medical Entity Recall",
        "prompt": "...",  # Uses {{audio}} + {{input}} + {{rx}}
        "output_schema": [...],  # Same schema as upload variant
    },
    # ... 4 more
]
```

Note: These constants do NOT include `app_id`, `listing_id`, `is_global`, etc. — those are set by the endpoint when creating evaluators on a specific listing.

---

## 2. Backend Endpoint: Seed Defaults

**File:** `backend/app/routes/evaluators.py`

### New Endpoint

```python
@router.post("/seed-defaults", response_model=list[EvaluatorResponse], status_code=201)
async def seed_defaults(
    listing_id: str = Query(..., alias="listingId"),
    db: AsyncSession = Depends(get_db),
):
    """Create recommended evaluators for a voice-rx listing based on its source type."""
```

**Logic:**

1. Load listing from DB. Verify it exists and is voice-rx.
2. Read `listing.source_type` ("upload" or "api").
3. Pick the matching constant: `VOICE_RX_UPLOAD_EVALUATORS` or `VOICE_RX_API_EVALUATORS`.
4. Check for existing evaluators on this listing with matching names (idempotency).
5. For each seed not already present: create `Evaluator` with:
   - `app_id = "voice-rx"`
   - `listing_id = listing.id`
   - `name` from seed constant
   - `prompt` from seed constant
   - `output_schema` from seed constant
   - `model_id = None` (uses default from settings)
   - `is_global = False`
   - `show_in_header = False` (except Critical Safety Audit → `True`)
6. Commit and return created evaluators.

**Idempotency:** Query existing evaluators for the listing. Skip any where `name` matches an existing evaluator on that listing. This prevents duplicates if the user clicks "Add recommended" twice or accidentally.

**Error cases:**
- Listing not found → 404
- Listing is not voice-rx → 400 "Seed evaluators are only available for voice-rx listings"
- Listing has unknown source_type → 400 "Listing source type '{source_type}' is not supported"

### Route Registration

This endpoint MUST be registered BEFORE the `/{evaluator_id}` routes to avoid FastAPI treating "seed-defaults" as a UUID path parameter. Place it in the "Variable Registry Endpoints" section (after line 71, alongside other non-UUID routes).

---

## 3. Fail-Fast on Unresolved Variables

**File:** `backend/app/services/evaluators/custom_evaluator_runner.py`

### Change Location: After `resolve_prompt` call (around line 200)

**BEFORE:**
```python
resolved = resolve_prompt(evaluator.prompt, resolve_ctx)
prompt_text = resolved["prompt"]

# Non-blocking validation: log unknown variables for observability
from app.services.evaluators.variable_registry import get_registry
validation = get_registry().validate_prompt(evaluator.prompt, app_id)
if validation["unknown_variables"]:
    logger.warning("Unknown variables in evaluator %s: %s", evaluator.name, validation["unknown_variables"])

has_audio = "{{audio}}" in evaluator.prompt and audio_bytes is not None
prompt_text = prompt_text.replace("{{audio}}", "[Audio file attached]")
```

**AFTER:**
```python
resolved = resolve_prompt(evaluator.prompt, resolve_ctx)
prompt_text = resolved["prompt"]

# Fail-fast: unresolved non-audio variables mean the listing is missing required data
unresolved = [v for v in resolved["unresolved_variables"] if v != "{{audio}}"]
if unresolved:
    var_names = ", ".join(unresolved)
    raise ValueError(
        f"Cannot run evaluator '{evaluator.name}': required data not available on this listing. "
        f"Unresolved variables: {var_names}"
    )

has_audio = "{{audio}}" in evaluator.prompt and audio_bytes is not None
prompt_text = prompt_text.replace("{{audio}}", "[Audio file attached]")
```

**Why `{{audio}}` is excluded:** The `{{audio}}` variable is always "unresolved" in the text because the resolver returns `None` for it (line 152 of prompt_resolver.py — it's handled by the runner directly via `generate_with_audio`). The runner replaces it after resolution.

**Error propagation:** The `ValueError` is caught by the existing `except Exception as e:` block (line 315 of custom_evaluator_runner.py), which:
1. Calls `finalize_eval_run(status="failed", error_message=error_msg)`
2. Logs the error
3. Re-raises

The user sees: "Cannot run evaluator 'Medical Entity Recall': required data not available on this listing. Unresolved variables: {{rx}}, {{input}}" in the evaluator card's error state.

### Remove old validation block

The `get_registry().validate_prompt()` call (lines 203-206) becomes unnecessary — unresolved variables are now caught directly from the resolver output. Remove it.

---

## 4. Frontend: API Client

**File:** `src/services/api/evaluatorsApi.ts`

### Add method:

```typescript
async seedDefaults(listingId: string): Promise<EvaluatorDefinition[]> {
  const data = await apiRequest<ApiEvaluator[]>(
    `/api/evaluators/seed-defaults?listingId=${listingId}`,
    { method: 'POST' },
  );
  return data.map(toEvaluatorDefinition);
}
```

---

## 5. Frontend: Zustand Store

**File:** `src/stores/evaluatorsStore.ts`

### Add method:

```typescript
seedDefaults: async (listingId: string) => {
  const seeded = await evaluatorsRepository.seedDefaults(listingId);
  set((state) => ({
    evaluators: [...state.evaluators, ...seeded],
  }));
  return seeded;
},
```

Add to the store interface as well:
```typescript
seedDefaults: (listingId: string) => Promise<EvaluatorDefinition[]>;
```

---

## 6. Frontend: EvaluatorsView — "Add Recommended" Banner

**File:** `src/features/evals/components/EvaluatorsView.tsx`

### Change the empty state (lines 117-153)

Add an "Add Recommended Evaluators" button above or alongside the existing "Add Evaluator" dropdown in the empty state. This is the primary CTA — more prominent than the existing dropdown.

**Design:**

```
┌──────────────────────────────────────────┐
│         [BarChart3 icon]                 │
│                                          │
│       No evaluators yet                  │
│                                          │
│  Add an evaluator to measure specific    │
│  dimensions of quality like recall,      │
│  factual integrity, or custom metrics.   │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  ★ Add Recommended Evaluators (5)  │  │  ← Primary CTA (brand accent)
│  └────────────────────────────────────┘  │
│                                          │
│  ┌───────────────────┐                   │
│  │  + Add Evaluator ▾ │                  │  ← Existing dropdown (secondary)
│  └───────────────────┘                   │
│                                          │
└──────────────────────────────────────────┘
```

### Implementation:

1. Add state: `const [isSeeding, setIsSeeding] = useState(false);`
2. Add handler:
   ```typescript
   const handleSeedDefaults = async () => {
     setIsSeeding(true);
     try {
       const seeded = await seedDefaults(listing.id);
       notificationService.success(`Added ${seeded.length} recommended evaluators`);
     } catch (err) {
       notificationService.error(
         err instanceof Error ? err.message : 'Failed to add recommended evaluators'
       );
     } finally {
       setIsSeeding(false);
     }
   };
   ```
3. Add button in empty state before the existing "Add Evaluator" dropdown:
   ```tsx
   <button
     onClick={handleSeedDefaults}
     disabled={isSeeding}
     className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[var(--color-brand-accent)] rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity"
   >
     {isSeeding ? 'Adding...' : 'Add Recommended Evaluators (5)'}
   </button>
   ```

### Show only for voice-rx

The seed endpoint only supports voice-rx. The button should only appear when `listing.appId === 'voice-rx'`. For kaira-bot, the existing empty state (with registry picker) remains unchanged.

---

## 7. Run Flows — What Changes, What Doesn't

### Single Evaluator Run (NO CHANGES)

Flow: EvaluatorCard "Run" button → `useEvaluatorRunner.handleRun()` → `evaluatorExecutor.execute()` → `submitAndPollJob('evaluate-custom', params)` → job worker → `custom_evaluator_runner.run_custom_evaluator()`.

The seeded evaluators use this exact flow. They are regular `Evaluator` DB rows with listing_id set. The only behavioral change is the fail-fast check (Section 3) — if variables can't resolve, the evaluator fails early with a clear message instead of sending garbage to the LLM.

### Batch Run via RunAllOverlay (NO CHANGES)

Flow: RunAllOverlay "Run N Evaluators" → `useSubmitAndRedirect.submit('evaluate-custom-batch', params)` → job worker → `custom_evaluator_runner.run_custom_eval_batch()` → calls `run_custom_evaluator()` per evaluator.

The seeded evaluators appear in the RunAllOverlay's evaluator list (it loads from the store, which loads all evaluators for the listing). The "Run All" button pre-selects all. No code changes needed — the overlay works with any evaluators on the listing.

### Batch Runner Custom Evaluators (NO CHANGES)

The batch_runner.py custom evaluator path (L324-383) is for kaira-bot `evaluate-batch` jobs. It loads evaluators by ID, resolves prompts with `{"messages": interleaved}` context, and runs them. This code path is not affected by voice-rx seed evaluators or variable cleanup.

### Job Polling (NO CHANGES)

`submitAndPollJob()` and `pollJobUntilComplete()` in `jobPolling.ts` are generic — they poll any job type. No changes needed.

### Error Propagation (IMPROVED)

**Before:** Unresolved variables stay as literal `{{variable}}` text in the prompt. LLM receives confusing input. May produce garbage output or throw a parsing error. The error message is cryptic (e.g., "Failed to parse JSON response").

**After:** Fail-fast check catches unresolved variables before the LLM call. Error message is clear: "Cannot run evaluator 'X': required data not available on this listing. Unresolved variables: {{rx}}, {{input}}". This message is saved in `eval_run.error_message` and displayed in the EvaluatorCard.

In batch mode (`run_custom_eval_batch`): the ValueError is caught by `run_custom_evaluator`'s `except Exception` handler, which finalizes the eval_run as failed and re-raises. The re-raise is caught by `_run_one`'s `except Exception` handler in the batch function, which logs and returns `status: "failed"`. The batch continues processing remaining evaluators. No change to this behavior.

---

## 8. Post-Implementation Validation

### Functional Tests

| # | Test | Steps | Expected |
|---|---|---|---|
| T1 | Seed upload evaluators | Open upload-flow listing → Evaluators tab (empty) → Click "Add Recommended Evaluators (5)" | 5 evaluators appear: MER, Factual Integrity, Negation Consistency, Temporal Precision, Critical Safety Audit. All use {{audio}} + {{transcript}} in prompts. |
| T2 | Seed API evaluators | Open API-flow listing → Evaluators tab (empty) → Click "Add Recommended" | 5 evaluators appear. All use {{audio}} + {{input}} + {{rx}} in prompts. |
| T3 | Idempotency | Click "Add Recommended" on a listing that already has seeded evaluators | No duplicates created. Toast: "Added 0 recommended evaluators" or skips silently. |
| T4 | Run single seed eval (upload) | On upload listing with transcript + audio → Run MER evaluator | Evaluator completes. Shows entity_recall_pct score, missed_entities array, reasoning. |
| T5 | Run single seed eval (API) | On API listing with api_response → Run MER evaluator | Evaluator completes. {{input}} resolves to api_response.input, {{rx}} resolves to api_response.rx. Shows scores. |
| T6 | Run All (batch) | On listing with 5 seeded evaluators → Click "Run All" → Select all → Submit | All 5 run in parallel via evaluate-custom-batch. Each produces results. RunAllOverlay redirects to runs page. |
| T7 | Missing data error (API eval on upload listing) | Fork an API-flow evaluator to an upload listing that has no api_response. Run it. | Fails fast with: "Cannot run evaluator 'X': required data not available. Unresolved variables: {{input}}, {{rx}}". Error shown in card. |
| T8 | Edit seeded evaluator | Open a seeded evaluator → Edit prompt → Save | Evaluator updated. Next run uses new prompt. No side effects on other listings. |
| T9 | Delete seeded evaluator | Delete one of the 5 seeded evaluators | Evaluator removed from listing. Can re-add via "Add Recommended" (idempotent — only creates missing ones). |
| T10 | Cancel during run | Start a seeded evaluator run → Cancel via card button | Job cancelled. Eval run finalized as cancelled. No orphaned state. |

### Regression Tests

| # | Test | What to Verify |
|---|---|---|
| R1 | Existing custom evaluators | User-created evaluators on other listings still run correctly. |
| R2 | Kaira-bot evaluators | All kaira-bot evaluators (seeded and user-created) still work. Chat Quality Analysis etc. unaffected. |
| R3 | Standard eval pipeline | Run evaluate-voice-rx on a listing. Pipeline completes normally. pipeline-internal variables (language_hint, script_preference) resolve correctly from prerequisites. |
| R4 | RunAllOverlay with mixed evaluators | Listing has 5 seeded + 2 user-created evaluators. "Run All" shows all 7 in overlay. Batch runs all correctly. |
| R5 | Job polling and progress | During batch run, frontend polling shows progress updates. Run IDs appear in job progress for redirect. |
| R6 | EvaluatorsView with evaluators | When listing already has evaluators, the "Add Recommended" banner does NOT appear (it's only in the empty state). The normal evaluator grid shows. |
| R7 | py_compile + lint | All modified Python files pass `python -m py_compile`. Frontend passes `npx tsc -b` and `npm run lint`. |

---

## 9. Files Changed Summary

| File | Change Type | Details |
|---|---|---|
| `backend/app/services/seed_defaults.py` | **Major addition** | Add `VOICE_RX_UPLOAD_EVALUATORS` (5) and `VOICE_RX_API_EVALUATORS` (5) constants with full prompts + output schemas |
| `backend/app/routes/evaluators.py` | **Addition** | New `POST /api/evaluators/seed-defaults` endpoint |
| `backend/app/services/evaluators/custom_evaluator_runner.py` | **Edit** | Add fail-fast check for unresolved variables (lines ~200-210). Remove old validation block. |
| `src/services/api/evaluatorsApi.ts` | **Addition** | Add `seedDefaults(listingId)` method |
| `src/stores/evaluatorsStore.ts` | **Addition** | Add `seedDefaults(listingId)` method to store interface and implementation |
| `src/features/evals/components/EvaluatorsView.tsx` | **Edit** | Add "Add Recommended Evaluators" button in empty state (voice-rx only) |

No model changes. No new tables. No migration. No changes to job worker, batch runner, RunAllOverlay, evaluator executor, job polling, or EvaluatorCard.
