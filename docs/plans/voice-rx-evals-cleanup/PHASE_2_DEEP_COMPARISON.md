# Phase 2: Deep Comparison Builder + Fix API Evaluation

**Goal**: Replace the coarse top-level-key comparison with a deep per-field comparison builder. Fix the API evaluation schema and prompt.

## Part A: Create `comparison_builder.py`

**Create**: `backend/app/services/evaluators/comparison_builder.py`

### Core Concept

The current critique comparison (runner L1144-1162) dumps entire `rx` fields as JSON. The LLM must figure out element alignment itself. This produces inconsistent, meaningless results.

**Fix**: Server-side deep comparison that:
1. Matches array items by a key field (e.g., medication `name`)
2. Compares individual sub-properties after matching
3. Handles object fields by comparing each sub-field
4. Handles scalar fields with direct comparison
5. Outputs a flat list of concrete per-field comparisons with stringified values

### Field Configuration

```python
# Array fields: match items by key, then compare sub-fields
ARRAY_FIELD_CONFIG = {
    "medications": {
        "key": "name",
        "fields": ["dosage", "frequency", "duration", "quantity", "schedule", "notes"],
    },
    "symptoms": {
        "key": "name",
        "fields": ["notes", "duration", "severity"],
    },
    "diagnosis": {
        "key": "name",
        "fields": ["notes", "since", "status"],
    },
    "medicalHistory": {
        "key": "name",
        "fields": ["type", "notes", "duration", "relation"],
    },
    "labResults": {
        "key": "testname",
        "fields": ["value"],
    },
    "labInvestigation": {
        "key": "testname",
        "fields": [],
    },
}

# Object fields: compare each sub-key individually
OBJECT_FIELD_CONFIG = {
    "vitalsAndBodyComposition": [
        "bloodPressure", "pulse", "temperature", "weight",
        "height", "spo2", "respRate", "ofc",
    ],
}

# Scalar fields: direct compare
SCALAR_FIELDS = ["followUp"]

# String arrays: compare as ordered lists
STRING_ARRAY_FIELDS = ["advice"]
```

### Key Functions

```python
@dataclass
class ComparisonEntry:
    """One field-level comparison line for prompt injection."""
    field_path: str       # "rx.medications[0].dosage"
    api_value: str        # Stringified value from API
    judge_value: str      # Stringified value from Judge
    match_hint: str       # "match" | "mismatch" | "api_only" | "judge_only"


def build_deep_comparison(api_rx: dict, judge_rx: dict) -> list[ComparisonEntry]:
    """Main entry point. Returns flat list of per-field comparison entries."""


def format_comparison_for_prompt(entries: list[ComparisonEntry]) -> str:
    """Format entries into structured text for prompt injection.

    Output format per entry:
      [N] FIELD: rx.medications[0].dosage
          API:   500mg
          JUDGE: 500 mg
          HINT:  match
    """
```

### Array Matching Algorithm

```python
def _compare_array_field(field_name, api_items, judge_items, key_field, sub_fields):
    """
    1. Build index: {normalized_key: (index, item)} for both API and Judge
    2. Normalize keys: lowercase, strip whitespace
    3. Matched keys: emit one entry per sub_field
    4. API-only keys: emit entries with judge_value="(not found)"
    5. Judge-only keys: emit entries with api_value="(not found)"
    """
```

### Value Stringification

All values are stringified before output:

```python
def _stringify(val) -> str:
    if val is None:
        return "(empty)"
    if isinstance(val, str):
        return val.strip() if val.strip() else "(empty)"
    if isinstance(val, (list, dict)):
        if not val:
            return "(empty)"
        return json.dumps(val, ensure_ascii=False)
    return str(val)
```

## Part B: Update `API_EVALUATION_SCHEMA` in `evaluation_constants.py`

Add `"type": "string"` to `apiValue` and `judgeValue`:

```python
"apiValue": {"type": "string", "description": "Exact string value from the comparison data above"},
"judgeValue": {"type": "string", "description": "Exact string value from the comparison data above"},
```

## Part C: Update `API_EVALUATION_PROMPT` in `evaluation_constants.py`

Rewrite to instruct LLM that fields are pre-aligned — its only job is to judge each pair:

```
You are an expert Medical Informatics Auditor evaluating rx JSON accuracy.

═══════════════════════════════════════════════════════════════════════════════
TASK: JUDGE PRE-ALIGNED FIELD COMPARISONS
═══════════════════════════════════════════════════════════════════════════════

Below is a server-built comparison. Section 1 compares transcripts. Section 2
lists individual structured-data fields, already matched and aligned for you.

{comparison}

═══════════════════════════════════════════════════════════════════════════════
YOUR JOB
═══════════════════════════════════════════════════════════════════════════════

For EACH field entry in the structured data section:
1. Judge whether the API value and Judge value agree in CLINICAL MEANING
   (not exact string match — "500mg" and "500 mg" are the same)
2. Classify severity:
   - none: Semantically equivalent
   - minor: Cosmetic only (formatting, abbreviation, casing)
   - moderate: Clinically meaningful difference, not dangerous
   - critical: Patient safety concern (wrong dosage, wrong drug, missed allergy)
3. Write a brief critique explaining your reasoning
4. Assign confidence (low/medium/high)
5. If possible, quote a short snippet from the transcripts as evidence

For the TRANSCRIPT section:
- Summarize whether transcripts are semantically equivalent
- List significant discrepancies with severity

═══════════════════════════════════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════════════════════════════════

- Output ONE entry per field in structuredComparison.fields
- Use the EXACT fieldPath string from the comparison data
- Copy apiValue and judgeValue as-is from the comparison
- Provide an overallAssessment summarizing API quality
- Output structure is controlled by the schema — just provide the data
```

## Part D: Update `_run_critique()` API Branch in `voice_rx_runner.py`

Replace the coarse loop (current L1144-1162) with:

```python
from app.services.evaluators.comparison_builder import (
    build_deep_comparison,
    format_comparison_for_prompt,
)

comparison_entries = build_deep_comparison(api_rx, judge_rx)

comparison_parts = [
    "=== SECTION 1: TRANSCRIPT COMPARISON ===",
    f"API TRANSCRIPT:\n{api_transcript}",
    f"\nJUDGE TRANSCRIPT:\n{judge_transcript}",
    "",
    "=== SECTION 2: FIELD-LEVEL STRUCTURED DATA (pre-aligned) ===",
    format_comparison_for_prompt(comparison_entries),
]
comparison_text = "\n".join(comparison_parts)
```

## Part E: Simplify `_extract_field_critiques_from_raw()`

Remove the "semantic audit shape" alternate path. Single clean path only:

```python
def _extract_field_critiques_from_raw(raw_critique: dict) -> list[dict]:
    """Extract field critiques from API critique response."""
    structured = raw_critique.get("structuredComparison") or {}
    return structured.get("fields", [])
```

## Wiring Verification

- [ ] `_update_progress()` — unchanged
- [ ] `PipelineStepError` — unchanged
- [ ] `LoggingLLMWrapper._save_log()` — unchanged
- [ ] `is_job_cancelled()` — unchanged
- [ ] Config snapshot — references updated constants
- [ ] Frontend `FieldCritiqueTable` — same `FieldCritique[]` shape, values now always strings
- [ ] `_build_summary()` — naturally handles the increased field count
