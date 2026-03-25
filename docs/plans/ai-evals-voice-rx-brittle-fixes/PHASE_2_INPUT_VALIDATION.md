# Phase 2 — Input Validation & Error Categorization

> Prevents bad inputs from causing silent failures or incorrect LLM dispatch.

## B1: Loose model family detection

### Problem

`llm_base.py:152-163` uses substring matching to detect Gemini model family:

```python
def _get_model_family(self) -> str:
    name = self.model_name.lower()
    if "3.1" in name:
        return "3.1"
    if "3.0" in name or "gemini-3-" in name or "gemini-3" in name.split("-"):
        return "3"
    return "2.5"  # Default fallback
```

Problems:
- A model like `"gemini-experimental-v3-alpha"` would match `"3"` in split
- The `"3.0" in name` check would match `"gemini-2.5-flash-v30"` (hypothetical)
- Default to 2.5 masks typos (e.g., `"gemni-2.5-flash"` → 2.5 silently)
- Gemini 2.0 models (`gemini-2.0-flash`) also fall to 2.5 thinking config, which
  is wrong because 2.0 doesn't support thinking at all

### Fix

Replace with explicit prefix/version matching and add a warning for unknown families.

```python
def _get_model_family(self) -> str:
    """Detect Gemini model family from model name.

    Returns "2.0", "2.5", "3", or "3.1" to determine thinking config format.
    - 2.0: No thinking support
    - 2.5: thinking_budget (int)
    - 3+: thinking_level (enum)
    """
    name = self.model_name.lower()

    # Check in order of specificity (most specific first)
    if "3.1" in name or "gemini-3-1" in name:
        return "3.1"
    if "3.0" in name or "gemini-3-0" in name:
        return "3"
    # Gemini 3 without minor version (e.g., "gemini-3-flash")
    if "gemini-3-" in name:
        return "3"
    if "2.5" in name or "gemini-2-5" in name:
        return "2.5"
    if "2.0" in name or "gemini-2-0" in name:
        return "2.0"

    logger.warning(
        "Unknown Gemini model family for '%s' — defaulting to 2.5 thinking config",
        self.model_name,
    )
    return "2.5"
```

Also update `_build_thinking_config` to handle the "2.0" family:

```python
def _build_thinking_config(self, thinking: str = "low"):
    if thinking == "off":
        return None

    family = self._get_model_family()

    if family == "2.0":
        # Gemini 2.0 does not support thinking — omit entirely
        return None

    # ... rest unchanged
```

### Files Changed
- `backend/app/services/evaluators/llm_base.py` — `_get_model_family()` (lines 152-163)
  and `_build_thinking_config()` (line 176 onward)

### Test Plan

**Test B1-1: Known model families**
```
"gemini-2.5-flash"       → "2.5"
"gemini-2.5-pro"         → "2.5"
"gemini-2.0-flash"       → "2.0"
"gemini-3-0-flash"       → "3"
"gemini-3.0-flash"       → "3"
"gemini-3-flash"         → "3"
"gemini-3-1-pro"         → "3.1"
"gemini-3.1-flash"       → "3.1"
```

**Test B1-2: Unknown model logs warning**
1. Create GeminiProvider with model_name `"gemini-experimental-foo"`
2. Call `_get_model_family()`
3. **Assert:** returns "2.5" AND warning logged

**Test B1-3: 2.0 models skip thinking entirely**
1. Create GeminiProvider with model_name `"gemini-2.0-flash"`
2. Call `_build_thinking_config("low")`
3. **Assert:** returns None (no thinking config)

**Test B1-4: Integration — evaluation with known model completes**
1. Run voice-rx evaluation with default model
2. **Assert:** completes without thinking config errors

---

## B6: Timeout overrides accepted without validation

### Problem

`voice_rx_runner.py:214-215` passes user-provided timeouts directly:

```python
if params.get("timeouts"):
    llm.set_timeouts(params["timeouts"])
```

And `llm_base.py:49-51` merges them blindly:

```python
def set_timeouts(self, timeouts: dict):
    self._timeouts.update(timeouts)
```

Negative, zero, non-numeric, or absurdly large values would cause:
- `asyncio.wait_for(timeout=0)` → immediate timeout
- `asyncio.wait_for(timeout=-1)` → ValueError
- `asyncio.wait_for(timeout=999999)` → 11-day timeout

### Fix

Add validation in `set_timeouts`:

```python
# Maximum allowed timeout: 10 minutes (600 seconds)
_MAX_TIMEOUT = 600
# Minimum: 5 seconds
_MIN_TIMEOUT = 5

VALID_TIMEOUT_KEYS = {"text_only", "with_schema", "with_audio", "with_audio_and_schema"}

def set_timeouts(self, timeouts: dict):
    """Override timeout values from user settings. Validates and clamps."""
    for key, value in timeouts.items():
        if key not in VALID_TIMEOUT_KEYS:
            logger.warning("Ignoring unknown timeout key: %s", key)
            continue
        if not isinstance(value, (int, float)):
            logger.warning("Ignoring non-numeric timeout for %s: %r", key, value)
            continue
        clamped = max(_MIN_TIMEOUT, min(_MAX_TIMEOUT, float(value)))
        if clamped != value:
            logger.info("Clamped timeout %s: %s → %s", key, value, clamped)
        self._timeouts[key] = clamped
```

### Files Changed
- `backend/app/services/evaluators/llm_base.py` — `set_timeouts()` (lines 49-51)

### Test Plan

**Test B6-1: Valid timeouts accepted**
```python
llm.set_timeouts({"text_only": 30, "with_audio": 120})
assert llm._timeouts["text_only"] == 30
assert llm._timeouts["with_audio"] == 120
```

**Test B6-2: Negative clamped to minimum**
```python
llm.set_timeouts({"text_only": -5})
assert llm._timeouts["text_only"] == 5  # _MIN_TIMEOUT
```

**Test B6-3: Oversized clamped to maximum**
```python
llm.set_timeouts({"with_audio": 99999})
assert llm._timeouts["with_audio"] == 600  # _MAX_TIMEOUT
```

**Test B6-4: Non-numeric ignored**
```python
llm.set_timeouts({"text_only": "fast"})
assert llm._timeouts["text_only"] == 60  # unchanged default
```

**Test B6-5: Unknown keys ignored**
```python
llm.set_timeouts({"bogus_key": 30})
assert "bogus_key" not in llm._timeouts
```

---

## B3: Normalization failure — no transient vs. user error distinction

### Problem

`voice_rx_runner.py:377-382` catches ALL normalization exceptions identically:

```python
except Exception as e:
    logger.warning("Normalization failed for %s: %s", listing_id, e)
    evaluation.setdefault("warnings", []).append(
        f"Normalization failed: {safe_error_message(e)}. Continuing without normalization."
    )
```

A user passing invalid scripts (e.g., `sourceScript: "klingon"`) gets the same
treatment as an API timeout. The user has no way to know if their config is wrong
vs. a transient issue that would succeed on retry.

### Fix

Categorize errors and include classification in the warning:

```python
except JobCancelledError:
    raise
except (LLMTimeoutError, ConnectionError, TimeoutError) as e:
    # Transient — would likely succeed on retry
    logger.warning("Normalization failed (transient) for %s: %s", listing_id, e)
    evaluation.setdefault("warnings", []).append(
        f"Normalization skipped (transient error, may succeed on retry): {safe_error_message(e)}"
    )
except ValueError as e:
    # User config error — won't succeed without changes
    logger.warning("Normalization failed (config error) for %s: %s", listing_id, e)
    evaluation.setdefault("warnings", []).append(
        f"Normalization skipped (configuration issue): {safe_error_message(e)}"
    )
except Exception as e:
    # Unknown — log full stack for debugging
    logger.warning("Normalization failed (unknown) for %s: %s", listing_id, e, exc_info=True)
    evaluation.setdefault("warnings", []).append(
        f"Normalization skipped: {safe_error_message(e)}"
    )
```

Also import `LLMTimeoutError` at the top of voice_rx_runner.py (it's already
imported from `llm_base` on line 28-30, just add it to the import list).

### Files Changed
- `backend/app/services/evaluators/voice_rx_runner.py` — lines 375-382

### Test Plan

**Test B3-1: Transient error produces correct warning category**
1. Mock normalization LLM call to raise `LLMTimeoutError`
2. Run evaluation with `normalize_original: true`
3. **Assert:** eval_run.status === "completed" (non-fatal)
4. **Assert:** result.warnings contains "transient error, may succeed on retry"

**Test B3-2: Config error produces correct warning category**
1. Run evaluation with `sourceScript: ""` (empty) and `normalize_original: true`
2. **Assert:** eval_run.status === "completed" (non-fatal)
3. **Assert:** result.warnings contains "configuration issue"

**Test B3-3: Normal normalization still works**
1. Run evaluation with valid scripts and `normalize_original: true`
2. **Assert:** eval_run.result.normalizedOriginal exists
3. **Assert:** no warnings in result

---

## B11: `repair_truncated_json` silently produces wrong JSON

### Problem

`response_parser.py:15-55` repairs truncated JSON by closing unclosed brackets.
If the LLM response was truly truncated (e.g., hit token limit), the repaired
JSON is syntactically valid but semantically wrong — missing fields, truncated
arrays, etc. No logging occurs.

### Fix

Add a `was_repaired` flag and log when repair happens. The repair function
already returns the repaired text. The caller `_safe_parse_json` (lines 95-123)
already returns a `(dict, bool)` tuple where the bool indicates repair.

The issue is that callers of `_safe_parse_json` **ignore the repair flag**.

In `voice_rx_runner.py:579-580`:
```python
parsed, _repaired = _safe_parse_json(response_text)
```

Fix: log when repaired, and include in evaluation metadata:

```python
parsed, was_repaired = _safe_parse_json(response_text)
if was_repaired:
    logger.warning(
        "Transcription response required JSON repair for listing %s — "
        "output may be incomplete",
        listing.id,
    )
```

Also in the critique parsing paths. For `parse_critique_response` and
`parse_api_critique_response` in `response_parser.py`, the repair already
happens inside those functions. Add logging there:

In `_safe_parse_json` (response_parser.py, line 110-116):
```python
# Stage 3: Repair truncated JSON
repaired = repair_truncated_json(text)
try:
    result = json.loads(repaired)
    logger.warning("JSON response required repair — output may be incomplete (first 200 chars: %s)", text[:200])
    return result, True
```

### Files Changed
- `backend/app/services/evaluators/response_parser.py` — `_safe_parse_json()` (add logging at repair stage)
- `backend/app/services/evaluators/voice_rx_runner.py` — lines 579-580 (log repair flag)

### Test Plan

**Test B11-1: Clean JSON produces no warning**
1. Parse valid JSON: `_safe_parse_json('{"key": "value"}')`
2. **Assert:** returns `({"key": "value"}, False)` — no repair
3. **Assert:** no warning logged

**Test B11-2: Truncated JSON logs warning**
1. Parse truncated: `_safe_parse_json('{"segments": [{"text": "hello"')`
2. **Assert:** returns parsed dict with `was_repaired=True`
3. **Assert:** warning logged containing "required repair"

**Test B11-3: Integration — truncated LLM response is logged**
1. Mock LLM to return truncated JSON (cut mid-array)
2. Run evaluation
3. **Assert:** backend logs contain "required repair"
4. **Assert:** eval_run still completes (repair is non-fatal)

---

## Phase 2 Completion Checklist

- [ ] B1 model family detection tightened and tested
- [ ] B6 timeout validation added and tested
- [ ] B3 normalization errors categorized and tested
- [ ] B11 JSON repair logging added and tested
- [ ] Backend starts cleanly: `docker compose up --build`
- [ ] Existing voice-rx evaluation completes (both flows)
- [ ] No regressions in LLM provider initialization
- [ ] Merge to `main`
