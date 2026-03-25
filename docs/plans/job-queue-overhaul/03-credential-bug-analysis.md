# Credential Resolution Bug Analysis

## The Bug: Silent Anthropic Failure

### Affected Code (3 locations — IDENTICAL pattern)

1. **`report_service.py:201-221`** — `_generate_narrative()`
2. **`report_service.py:491-511`** — `_generate_custom_eval_narrative()`
3. **`reports.py:354-369`** — `generate_cross_run_ai_summary()` endpoint

### The Pattern

```python
try:
    settings = await get_llm_settings_from_db(
        auth_intent="managed_job",
        provider_override=llm_provider or None,
    )
except RuntimeError:
    sa_path = _detect_service_account_path()
    effective_prov = llm_provider or "gemini"
    if effective_prov == "gemini" and sa_path:
        # Gemini-only fallback — creates manual settings dict
        settings = {"provider": "gemini", ...}
    else:
        # ALL OTHER PROVIDERS: silently skip/warn
        logger.warning("Narrative skipped: no credentials for %s", effective_prov)
        return None, None  # SILENT FAILURE
```

### Why RuntimeError Would Be Thrown

`get_llm_settings_from_db()` raises `RuntimeError` when:
1. No `llm-settings` row in `settings` table at `app_id=""`
2. Row exists but has NO API key for the requested provider override

### Impact by Provider

| Provider | DB Has Key | DB Missing Key | SA Available |
|----------|-----------|----------------|--------------|
| Gemini | Works | Uses SA fallback | Yes |
| Anthropic | Works | **SILENT SKIP** | N/A (no SA) |
| OpenAI | Works | **SILENT SKIP** | N/A (no SA) |
| Azure | Works | **SILENT SKIP** | N/A (no SA) |

### Contrast with Other Runners

| Runner | Credential Pattern | On Failure |
|--------|-------------------|------------|
| batch_runner.py | `get_llm_settings_from_db()` — NO try/except | **Raises** → job fails with error |
| adversarial_runner.py | `get_llm_settings_from_db()` — NO try/except | **Raises** → job fails with error |
| voice_rx_runner.py | `get_llm_settings_from_db()` — NO try/except | **Raises** → job fails with error |
| custom_evaluator_runner.py | `get_llm_settings_from_db()` — NO try/except | **Raises** → job fails with error |
| **report_service.py** | try/except → Gemini SA fallback | **Silent None** |
| **reports.py (cross-run)** | try/except → Gemini SA fallback | **Re-raises** (slightly better) |

### Root Cause

The report service was written when Gemini was the only provider and SA-only
installations were common. The try/except was added as a convenience for
"SA-only, no settings saved" scenario. When Anthropic/OpenAI were added,
the fallback was never updated.

### Fix Strategy

**Remove the Gemini-only fallback hack.** Let `get_llm_settings_from_db()` errors
propagate naturally. This is consistent with ALL other runners.

If the user hasn't configured API keys in Settings, the job should FAIL with:
- Error message: "No LLM settings found. Configure API keys in Settings."
- This error surfaces to the frontend via job.errorMessage
- User knows exactly what to do

The outer `except Exception` at report_service.py:261 catches all other LLM errors
(network, rate limit, etc.) and returns None — this is FINE because the report
still generates without narrative, and the warning toast tells the user.

The RuntimeError (no credentials) is a CONFIG error, not a transient error.
It should FAIL loudly, not silently skip.
