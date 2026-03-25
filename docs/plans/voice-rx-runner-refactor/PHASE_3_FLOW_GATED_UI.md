# Phase 3: Flow-Gated UI

## Goal

Ensure the frontend UI only shows flow-appropriate prompts, schemas, variables, and actions. A user working with an upload-flow listing should never see API-specific options, and vice versa. The `Listing.sourceType` gates everything.

## Dependency

Phase 2 must be complete. Display components use `flowType` for rendering.

## Current State (Problems)

### Prompt Selection (EvaluationOverlay)

1. **Line 239**: Comment says `// no sourceType filter - Phase 2` — prompts are loaded without sourceType filtering
2. **Lines 241-242**: `transcriptionPrompts = allPrompts.filter(p => p.promptType === "transcription")` — no sourceType filter
3. **Lines 490-491**: Default auto-selection DOES use sourceType: `p.isDefault && p.sourceType === sourceType` — but the dropdown still shows ALL prompts

### Schema Selection

4. `SchemaSelector.tsx` correctly filters by `sourceType` when the prop is passed
5. BUT: The Settings page (`SchemasTab.tsx`) shows ALL schemas without flow grouping

### Prompt/Schema Backend Routes

6. `GET /api/prompts` has NO `source_type` query parameter — returns all prompts for an app
7. `GET /api/schemas` same — no `source_type` filter
8. New prompts/schemas created by users have `source_type: null` — they're "untagged"

### Variable Registry

9. `variableRegistry.ts` correctly knows which variables are per-flow
10. But no UI prevents a user from writing `{{time_windows}}` in an API-flow prompt — they'd just get an empty substitution

### Listing Actions

11. `ListingPage.tsx` line 314: When `sourceType === 'pending'`, shows both "Fetch from API" and "Upload Transcript" — correct
12. But after choosing one flow, the other action remains available (no locking)

## Changes

### 3.1 Backend: Add `source_type` Query Filter to Prompt/Schema Routes

**File: `backend/app/routes/prompts.py`**

```python
@router.get("/api/prompts")
async def list_prompts(
    app_id: str = Query(...),
    prompt_type: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),  # NEW
    db: AsyncSession = Depends(get_db),
):
    query = select(Prompt).where(Prompt.app_id == app_id)
    if prompt_type:
        query = query.where(Prompt.prompt_type == prompt_type)
    if source_type:
        # Return prompts that match this source_type OR are untagged (null)
        query = query.where(
            or_(Prompt.source_type == source_type, Prompt.source_type.is_(None))
        )
    query = query.order_by(Prompt.prompt_type, Prompt.is_default.desc(), Prompt.version.desc())
    result = await db.execute(query)
    return [PromptResponse.model_validate(p) for p in result.scalars()]
```

**File: `backend/app/routes/schemas.py`** — identical pattern.

### 3.2 Frontend: Filter Prompts by sourceType in Store

**File: `src/stores/promptsStore.ts`**

The `_sourceType` parameter is already accepted but ignored. Implement filtering:

```typescript
getPromptsByType: (appId, promptType, sourceType?) => {
  const prompts = get().prompts;
  return prompts.filter(p => {
    if (p.promptType !== promptType) return false;
    // If sourceType specified, filter: match or untagged (null)
    if (sourceType) {
      return p.sourceType === sourceType || !p.sourceType;
    }
    return true;
  });
}
```

**File: `src/stores/schemasStore.ts`** — add same `sourceType` filter to `getSchemasByType`.

### 3.3 Frontend: Filter Prompt Dropdowns in EvaluationOverlay

**File: `src/features/evals/components/EvaluationOverlay.tsx`**

Change the prompt filtering memos to include `sourceType`:

```typescript
// Line 241-242, change from:
const transcriptionPrompts = useMemo(
  () => allPrompts.filter((p) => p.promptType === "transcription"),
  [allPrompts]
);

// To:
const transcriptionPrompts = useMemo(
  () => allPrompts.filter((p) =>
    p.promptType === "transcription" &&
    (p.sourceType === sourceType || !p.sourceType)
  ),
  [allPrompts, sourceType]
);

// Same for evaluationPrompts
const evaluationPrompts = useMemo(
  () => allPrompts.filter((p) =>
    p.promptType === "evaluation" &&
    (p.sourceType === sourceType || !p.sourceType)
  ),
  [allPrompts, sourceType]
);
```

### 3.4 Frontend: Tag New Prompts/Schemas with sourceType

When a user creates a new prompt or schema from within the EvaluationOverlay (inline editor), tag it with the current listing's `sourceType`:

**File: `src/features/evals/components/EvaluationOverlay.tsx`** — wherever `promptsApi.create()` or `schemasApi.create()` is called:

```typescript
// When saving a new prompt from the overlay
await promptsRepository.create({
  appId,
  promptType: 'transcription',
  name: newPromptName,
  prompt: newPromptText,
  sourceType: sourceType,  // TAG with current flow
});
```

Same for schema creation.

### 3.5 Frontend: Variable Warnings in Prompt Editor

When a user is editing a prompt in the EvaluationOverlay, show a warning if they reference variables not available for the current flow.

The variable validation logic already exists in `variableRegistry.ts`:
- `getDisabledVariablesForStep()` returns a map of disabled variables with reasons

**Display**: In the prompt editor area, below the textarea, show disabled variable warnings:

```typescript
// Already computed in EvaluationOverlay as transcriptionValidation / evaluationValidation
// Just render the warnings more prominently

{validation.disabledVars.size > 0 && (
  <div className="mt-1 p-2 rounded bg-[var(--surface-warning)] border border-[var(--border-warning)]">
    <p className="text-[10px] text-[var(--color-warning)] font-medium">
      Variables not available for {sourceType} flow:
    </p>
    {Array.from(validation.disabledVars.entries()).map(([varKey, reason]) => (
      <p key={varKey} className="text-[10px] text-[var(--text-muted)] ml-2">
        <code>{varKey}</code> — {reason}
      </p>
    ))}
  </div>
)}
```

### 3.6 Frontend: Settings Page Flow Grouping

**File: `src/features/settings/components/PromptsTab.tsx`**

Group prompts by source type within each prompt type:

```typescript
// Within each promptType group, sub-group by sourceType
const uploadPrompts = prompts.filter(p => p.sourceType === 'upload');
const apiPrompts = prompts.filter(p => p.sourceType === 'api');
const untaggedPrompts = prompts.filter(p => !p.sourceType);

// Render with visual group headers:
// ┌─ Upload Flow ──────────────────┐
// │  Upload: Transcription (v1)    │
// └────────────────────────────────┘
// ┌─ API Flow ─────────────────────┐
// │  API: Transcription (v1)       │
// └────────────────────────────────┘
// ┌─ Custom (Any Flow) ────────────┐
// │  My Custom Prompt              │
// └────────────────────────────────┘
```

**File: `src/features/settings/components/SchemasTab.tsx`** — same grouping.

### 3.7 Seed Defaults: Verify Tagging

**File: `backend/app/services/seed_defaults.py`**

Verify ALL seeded prompts and schemas have correct `source_type`:

| Name | prompt_type | Expected source_type | Current |
|------|-------------|---------------------|---------|
| Upload: Transcription | transcription | `upload` | `upload` |
| Upload: Evaluation | evaluation | `upload` | `upload` |
| Upload: Extraction | extraction | `upload` | `upload` |
| API: Transcription | transcription | `api` | `api` |
| API: Evaluation | evaluation | `api` | `api` |
| Upload: Transcript Schema | transcription | `upload` | `upload` |
| Upload: Evaluation Schema | evaluation | `upload` | `upload` |
| Upload: Extraction Schema | extraction | `upload` | `upload` |
| API: Transcript Schema | transcription | `api` | `api` |
| API: Critique Schema | evaluation | `api` | `api` |

If any are missing `source_type`, fix in seed_defaults.

### 3.8 Normalization Checkbox: Enable for API Flow

**File: `src/features/evals/components/EvaluationOverlay.tsx`**

Currently line 336-337:
```typescript
const [normalizationEnabled, setNormalizationEnabled] = useState(
  sourceType === "upload"  // Enable by default for upload flow
);
```

With Phase 1 enabling normalization for API flow, keep the default as-is (upload = on, API = off) but ensure the checkbox is clearly available and labeled for both flows. No hiding needed — the backend now handles both.

### 3.9 EvaluationOverlay: Hide Flow-Irrelevant Options

For upload flow:
- Hide "Derive Schema from API Response" button (only makes sense for API)
- `useSegments` checkbox is relevant — show

For API flow:
- Hide `useSegments` checkbox (segments don't apply)
- Show "Derive Schema from API Response" button

Most of this gating already exists in the overlay. Audit and confirm:

```typescript
// useSegments: only for upload
{sourceType === 'upload' && (
  <Checkbox label="Use time-aligned segments" ... />
)}

// Derive schema: only for API
{sourceType === 'api' && listing.apiResponse && (
  <Button onClick={handleDeriveSchema}>Derive from API Response</Button>
)}
```

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/routes/prompts.py` | **MODIFY** | Add `source_type` query parameter |
| `backend/app/routes/schemas.py` | **MODIFY** | Add `source_type` query parameter |
| `src/stores/promptsStore.ts` | **MODIFY** | Implement `sourceType` filtering in getter |
| `src/stores/schemasStore.ts` | **MODIFY** | Implement `sourceType` filtering in getter |
| `src/features/evals/components/EvaluationOverlay.tsx` | **MODIFY** | Filter dropdowns, tag new items, hide irrelevant options |
| `src/features/settings/components/PromptsTab.tsx` | **MODIFY** | Group by sourceType |
| `src/features/settings/components/SchemasTab.tsx` | **MODIFY** | Group by sourceType |
| `backend/app/services/seed_defaults.py` | **VERIFY** | Confirm all source_type tags correct |

## Verification Checklist

### Prompt/Schema Filtering
- [ ] Create an upload-flow listing → open eval overlay → transcription prompt dropdown shows ONLY upload + untagged prompts
- [ ] Create an API-flow listing → open eval overlay → transcription prompt dropdown shows ONLY API + untagged prompts
- [ ] Upload prompts are NOT visible in API-flow eval overlay
- [ ] API prompts are NOT visible in upload-flow eval overlay
- [ ] User-created prompts (sourceType=null) appear in BOTH flows

### Schema Filtering
- [ ] SchemaSelector in eval overlay filters by sourceType (already works — verify)
- [ ] Upload schemas don't appear in API-flow overlay
- [ ] API schemas don't appear in upload-flow overlay

### Tagging
- [ ] Create a new prompt from within upload-flow eval overlay → `sourceType: "upload"` is set
- [ ] Create a new prompt from within API-flow eval overlay → `sourceType: "api"` is set
- [ ] Create a new schema from Settings page → `sourceType: null` (no flow context)

### Variable Warnings
- [ ] Edit a prompt in API-flow eval overlay → type `{{time_windows}}` → warning appears
- [ ] Edit a prompt in upload-flow eval overlay → type `{{structured_output}}` → warning appears
- [ ] Variables compatible with both flows → no warning

### Settings Page
- [ ] PromptsTab groups prompts by flow (Upload / API / Custom)
- [ ] SchemasTab groups schemas by flow
- [ ] Default prompts show correct flow badge

### Backend Route
- [ ] `GET /api/prompts?app_id=voice-rx&source_type=upload` returns only upload + null prompts
- [ ] `GET /api/prompts?app_id=voice-rx&source_type=api` returns only API + null prompts
- [ ] `GET /api/prompts?app_id=voice-rx` (no source_type) returns all prompts
