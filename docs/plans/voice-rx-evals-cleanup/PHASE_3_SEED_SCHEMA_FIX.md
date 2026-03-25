# Phase 3: Fix `seed_defaults.py` API Transcription Schema

**Goal**: Add `required` fields to the `rx` object in the API transcription schema so Gemini cannot return a sparse/empty `rx: {}`.

## The Bug (BUG 1)

**File**: `backend/app/services/seed_defaults.py` lines 281-395

The seeded "API: Transcript Schema" defines `rx` as:
```python
"rx": {
    "type": "object",
    "description": "Structured prescription and clinical data...",
    "properties": {
        "symptoms": { ... },
        "medications": { ... },
        "diagnosis": { ... },
        # ... 12 more fields
    },
    # ❌ NO "required" array!
}
```

Gemini's structured output mode treats all `rx` sub-fields as optional. A response like `{"input": "transcript text", "rx": {}}` is schema-valid. When this sparse judge output gets compared against the rich real API `rx`, everything is a mismatch → noise.

## The Fix

Add `"required"` to the `rx` object listing all core clinical fields:

```python
"rx": {
    "type": "object",
    "description": "Structured prescription and clinical data extracted from the conversation",
    "properties": {
        # ... all existing properties unchanged ...
    },
    "required": [
        "symptoms",
        "medications",
        "diagnosis",
        "medicalHistory",
        "vitalsAndBodyComposition",
        "labResults",
        "labInvestigation",
        "advice",
        "followUp",
    ],
},
```

### What We Are NOT Adding `required` To

- Individual item sub-fields (e.g., medication `dosage`, `frequency`) — these are intentionally optional. If the audio doesn't mention a dosage, the LLM should omit it, not hallucinate.
- Rarely-used fields: `examinations`, `vaccinations`, `others`, `dynamicFields` — these are uncommon in typical consultations and adding them as required would force empty arrays/objects unnecessarily.

### What This Achieves

With `required`, Gemini must return at least:
```json
{
  "input": "full transcript text",
  "rx": {
    "symptoms": [],
    "medications": [],
    "diagnosis": [],
    "medicalHistory": [],
    "vitalsAndBodyComposition": {},
    "labResults": [],
    "labInvestigation": [],
    "advice": [],
    "followUp": ""
  }
}
```

Even empty arrays/objects are fine — the deep comparison builder (Phase 2) correctly handles empty vs populated fields. The point is the STRUCTURE is present, so the builder has data to work with.

## Auto-Update Mechanism

The `_seed_schemas()` function already handles schema updates idempotently:

```python
# seed_defaults.py L928-937
for s_def in VOICE_RX_SCHEMAS:
    name = s_def["name"]
    if name in existing_schemas:
        existing = existing_schemas[name]
        if existing.schema_data != s_def["schema_data"]:
            existing.schema_data = s_def["schema_data"]
            logger.info("Updated schema_data for '%s'", name)
```

On next backend startup, the seed function detects the schema change and updates the DB row. No migration needed.

## Wiring Verification

- `_load_default_schema()` in `voice_rx_runner.py` (L354-368) loads from DB — gets updated schema after restart
- `_run_transcription()` passes schema to `llm.generate_with_audio(json_schema=schema)` — Gemini enforces the updated schema
- Judge output will now always include all core `rx` fields
- `build_deep_comparison()` (Phase 2) will have complete data to compare
- Frontend is unaffected — only reads critique output, not the transcription schema
- Config snapshot `EvalRun.config.schemas.transcription` will reflect the updated schema for new runs
- Old runs are unaffected — their config snapshot preserves the old schema

## Risk Assessment

**LOW risk**. This is a schema-only change to seed data. The seed update mechanism is battle-tested (used for every migration phase). The worst case is Gemini returning slightly more verbose output, which is the desired behavior.

## Verification Steps

1. Start backend: `docker compose up --build`
2. Check logs for: `Updated schema_data for 'API: Transcript Schema'`
3. Run an API flow evaluation
4. Inspect `EvalRun.result.judgeOutput.structuredData` — should have all core rx fields
5. Inspect `EvalRun.config.schemas.transcription` — should include the `required` array on `rx`
