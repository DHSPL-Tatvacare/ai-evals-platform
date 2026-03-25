# Phase 1: Extract Constants to `evaluation_constants.py`

**Goal**: Pure refactor. Move all hardcoded constants out of `voice_rx_runner.py` into a dedicated module. Zero behavior change.

## New File

**Create**: `backend/app/services/evaluators/evaluation_constants.py`

### What Moves There (from `voice_rx_runner.py`)

| Constant | Current Lines | Type | Purpose |
|----------|--------------|------|---------|
| `SCRIPT_DISPLAY_NAMES` | 46-71 | dict | Script ID → human-readable name map (23 entries) |
| `_resolve_script_name()` | 74-78 | function | Looks up script display name (tightly coupled to dict above) |
| `NORMALIZATION_PROMPT` | 85-105 | str template | Segment-level transliteration instruction. Format vars: `{target_script}`, `{source_instruction}`, `{language}`, `{transcript_json}` |
| `NORMALIZATION_PROMPT_PLAIN` | 107-126 | str template | Plain-text transliteration instruction. Format vars: `{target_script}`, `{source_instruction}`, `{language}`, `{transcript_text}` |
| `_build_normalization_schema()` | 129-149 | function | Builds segment normalization JSON schema dynamically |
| `_build_normalization_schema_plain()` | 152-163 | function | Builds plain-text normalization JSON schema dynamically |
| `UPLOAD_EVALUATION_PROMPT` | 168-212 | str template | Upload critique instruction. Format vars: `{segment_count}`, `{comparison_table}` |
| `UPLOAD_EVALUATION_SCHEMA` | 214-248 | dict | Upload critique JSON schema (segments array + overallAssessment) |
| `API_EVALUATION_PROMPT` | 250-277 | str template | API critique instruction. Format vars: `{comparison}` |
| `API_EVALUATION_SCHEMA` | 279-332 | dict | API critique JSON schema (transcriptComparison + structuredComparison + overallAssessment) |

### Module Structure

```python
"""Evaluation constants for the voice-rx pipeline.

All hardcoded prompts, schemas, display names, and normalization templates
for both upload and API flows. Separated from voice_rx_runner.py for
maintainability.
"""

# ═══════════════════════════════════════════════════════════════
# SCRIPT DISPLAY NAMES
# ═══════════════════════════════════════════════════════════════

SCRIPT_DISPLAY_NAMES = { ... }

def resolve_script_name(script_id: str) -> str:
    """Convert script ID to human-readable name for prompts."""
    ...

# ═══════════════════════════════════════════════════════════════
# NORMALIZATION PROMPTS & SCHEMAS
# ═══════════════════════════════════════════════════════════════

NORMALIZATION_PROMPT = """..."""
NORMALIZATION_PROMPT_PLAIN = """..."""

def build_normalization_schema(target_script: str) -> dict: ...
def build_normalization_schema_plain(target_script: str) -> dict: ...

# ═══════════════════════════════════════════════════════════════
# UPLOAD FLOW — EVALUATION PROMPT & SCHEMA
# ═══════════════════════════════════════════════════════════════

UPLOAD_EVALUATION_PROMPT = """..."""
UPLOAD_EVALUATION_SCHEMA = { ... }

# ═══════════════════════════════════════════════════════════════
# API FLOW — EVALUATION PROMPT & SCHEMA
# ═══════════════════════════════════════════════════════════════

API_EVALUATION_PROMPT = """..."""
API_EVALUATION_SCHEMA = { ... }
```

### Naming Convention

Private functions in `voice_rx_runner.py` become public in the constants module (they're the module's API):
- `_resolve_script_name()` → `resolve_script_name()`
- `_build_normalization_schema()` → `build_normalization_schema()`
- `_build_normalization_schema_plain()` → `build_normalization_schema_plain()`

## Changes to `voice_rx_runner.py`

### Delete

Lines 43-332 (all constants, helper functions, schema builders)

### Add Import

```python
from app.services.evaluators.evaluation_constants import (
    SCRIPT_DISPLAY_NAMES,
    resolve_script_name,
    NORMALIZATION_PROMPT,
    NORMALIZATION_PROMPT_PLAIN,
    build_normalization_schema,
    build_normalization_schema_plain,
    UPLOAD_EVALUATION_PROMPT,
    UPLOAD_EVALUATION_SCHEMA,
    API_EVALUATION_PROMPT,
    API_EVALUATION_SCHEMA,
)
```

### Rename References

All internal references update from private to public names:
- `_resolve_script_name(x)` → `resolve_script_name(x)`
- `_build_normalization_schema(x)` → `build_normalization_schema(x)`
- `_build_normalization_schema_plain(x)` → `build_normalization_schema_plain(x)`

**Exact call sites** (line numbers are pre-extraction, will shift after deletion):
- L78: `_resolve_script_name()` — rename to `resolve_script_name()`
- L551: `UPLOAD_EVALUATION_SCHEMA if flow.requires_segments else API_EVALUATION_SCHEMA` — no change needed (same names)
- L975: `NORMALIZATION_PROMPT.format(...)` — no change needed
- L981: `_build_normalization_schema(target_display)` — rename
- L1011: `NORMALIZATION_PROMPT_PLAIN.format(...)` — no change needed
- L1017: `_build_normalization_schema_plain(target_display)` — rename
- L1074: `UPLOAD_EVALUATION_PROMPT.format(...)` — no change needed
- L1082: `json_schema=UPLOAD_EVALUATION_SCHEMA` — no change needed
- L1164: `API_EVALUATION_PROMPT.format(...)` — no change needed
- L1168: `json_schema=API_EVALUATION_SCHEMA` — no change needed

## Verification

1. `voice_rx_runner.py` should shrink by ~290 lines (from ~1272 to ~980)
2. `evaluation_constants.py` should be ~290 lines
3. Both upload and API flows should produce identical results to before
4. Config snapshot in `EvalRun.config` should still contain the schema dicts
5. No import errors — run `docker compose up --build` to verify
