# Fix 1: Remove Wrong `app_id` From Report Callers

## The Bug

3 callers pass `app_id=run.app_id` (e.g. `"kaira-bot"`) to
`get_llm_settings_from_db`. LLM settings only exist at global scope
(`app_id=""`). The query finds nothing and throws `RuntimeError`.

Every other caller in the codebase (voice_rx_runner, batch_runner,
adversarial_runner, custom_evaluator_runner, job_worker, llm routes)
either passes `app_id=None` or omits it — and they all work fine.

## The Fix

Remove `app_id=run.app_id` from the 3 broken callers. LLM settings are
global — callers should not pass an app-specific scope.

### Call site 1: `report_service.py` — `_generate_narrative` (~line 202)

```python
# Before:
settings = await get_llm_settings_from_db(
    app_id=run.app_id,
    auth_intent="managed_job",
    provider_override=llm_provider or None,
)

# After:
settings = await get_llm_settings_from_db(
    auth_intent="managed_job",
    provider_override=llm_provider or None,
)
```

### Call site 2: `report_service.py` — `_generate_custom_eval_narrative` (~line 487)

```python
# Before:
settings = await get_llm_settings_from_db(
    app_id=run.app_id,
    auth_intent="managed_job",
)

# After:
settings = await get_llm_settings_from_db(
    auth_intent="managed_job",
)
```

### Call site 3: `routes/reports.py` — cross-run summary (~line 350)

```python
# Before:
settings = await get_llm_settings_from_db(
    app_id=request.app_id,
    auth_intent="managed_job",
)

# After:
settings = await get_llm_settings_from_db(
    auth_intent="managed_job",
)
```

## Verification

1. Generate a report with Anthropic for a `kaira-bot` run — narrative should
   generate successfully.
2. Generate a report with Gemini — should still work (regression check).
3. Backend logs should show `Auth resolved: intent=managed_job method=api_key
   provider=anthropic` instead of the old `RuntimeError`.

## Scope

- **2 files changed**: `report_service.py`, `routes/reports.py`
- **3 lines changed** (remove `app_id=` parameter from each call)
