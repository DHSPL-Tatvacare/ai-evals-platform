# Fix 2: Make `except RuntimeError` Fallback Provider-Aware

## The Bug

The `except RuntimeError` blocks in `_generate_narrative` and
`_generate_custom_eval_narrative` construct a fallback settings dict with
`api_key=""` and rely on `service_account_path` from SA detection. This
only works for Gemini. For Anthropic/OpenAI/Azure, it creates a broken
provider with an empty API key that fails silently.

After Fix 1, this fallback rarely fires (only on truly exceptional errors
like DB connection failure). But when it does fire, it should fail clearly
instead of creating a broken provider.

## The Fix

Guard the fallback: only construct the SA-based settings dict when the
effective provider is Gemini AND an SA path exists. Otherwise, log and
skip narrative generation.

### `_generate_narrative` (~line 207)

```python
# Before:
except RuntimeError:
    sa_path = _detect_service_account_path()
    if not sa_path and not llm_provider:
        raise
    settings = {
        "provider": llm_provider or "gemini",
        "selected_model": llm_model or "",
        "api_key": "",
        "service_account_path": sa_path,
    }

# After:
except RuntimeError:
    sa_path = _detect_service_account_path()
    effective_prov = llm_provider or "gemini"
    if effective_prov == "gemini" and sa_path:
        settings = {
            "provider": "gemini",
            "selected_model": llm_model or "",
            "api_key": "",
            "service_account_path": sa_path,
        }
    else:
        logger.warning(
            "Narrative skipped: no credentials for %s (settings lookup failed)",
            effective_prov,
        )
        return None, None
```

Apply the same pattern to `_generate_custom_eval_narrative` (~line 491),
returning `report` instead of `None, None`.

And to `routes/reports.py` cross-run summary (~line 354), raising the
original error instead of returning.

## Scope

- **2 files changed**: `report_service.py`, `routes/reports.py`
- **~15 lines changed** across 3 except blocks
