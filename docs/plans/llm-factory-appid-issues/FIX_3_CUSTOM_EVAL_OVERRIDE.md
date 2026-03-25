# Fix 3: Add Missing `provider_override` to Custom Eval Narrative

## The Bug

`_generate_custom_eval_narrative` calls `get_llm_settings_from_db` without
`provider_override`. When the user selects Anthropic for report generation,
the custom eval narrative resolves the API key for the **saved default
provider** instead of the user's selection.

The main narrative call (`_generate_narrative`) already passes
`provider_override=llm_provider or None`. This call doesn't.

## The Fix

One line — add the missing parameter.

### `report_service.py` — `_generate_custom_eval_narrative` (~line 487)

```python
# Before:
settings = await get_llm_settings_from_db(
    auth_intent="managed_job",
)

# After:
settings = await get_llm_settings_from_db(
    auth_intent="managed_job",
    provider_override=llm_provider or None,
)
```

Note: This call site also has Fix 1 applied (app_id removed). After both
fixes, it matches the pattern used by `_generate_narrative`.

## Scope

- **1 file changed**: `report_service.py`
- **1 line added**
