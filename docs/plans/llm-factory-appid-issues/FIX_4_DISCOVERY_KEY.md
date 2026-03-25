# Fix 4: Add `provider_override` to Model Discovery

## The Bug

`_get_provider_key_from_db("anthropic")` calls `get_llm_settings_from_db()`
without `provider_override`. The returned `api_key` is for the saved default
provider. It then checks `if db_settings.get("provider") == provider` — if
the default isn't "anthropic", returns `""`.

This means model discovery for non-default providers falls through to
hardcoded fallback models instead of live API discovery.

## The Fix

Pass `provider_override` so the correct per-provider key is returned.
Remove the now-redundant provider equality check.

### `routes/llm.py` — `_get_provider_key_from_db` (~line 252)

```python
# Before:
async def _get_provider_key_from_db(provider: str) -> str:
    try:
        from app.services.evaluators.settings_helper import get_llm_settings_from_db
        db_settings = await get_llm_settings_from_db()
        if db_settings.get("provider") == provider:
            return db_settings.get("api_key", "")
    except Exception:
        pass
    return ""

# After:
async def _get_provider_key_from_db(provider: str) -> str:
    try:
        from app.services.evaluators.settings_helper import get_llm_settings_from_db
        db_settings = await get_llm_settings_from_db(provider_override=provider)
        return db_settings.get("api_key", "")
    except Exception:
        pass
    return ""
```

## Scope

- **1 file changed**: `routes/llm.py`
- **~3 lines changed**
