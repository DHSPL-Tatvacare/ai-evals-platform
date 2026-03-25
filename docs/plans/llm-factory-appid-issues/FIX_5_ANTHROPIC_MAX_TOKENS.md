# Fix 5: Bump Anthropic `max_tokens` From 8192 to 16384

## The Bug

`AnthropicProvider._sync_generate` and `_sync_generate_json` hardcode
`max_tokens: 8192`. Report narratives for runs with many threads can exceed
this, producing truncated JSON that fails `json.loads()` and silently drops
the narrative.

The Anthropic API requires `max_tokens` (unlike OpenAI/Gemini where it's
optional). 8192 is artificially low — Sonnet supports 64K, Opus 32K.

## The Fix

Change `8192` to `16384` in both methods. That's it.

Anthropic bills per token **used**, not requested. A higher limit has zero
cost impact — the model still stops when it's done generating.

No model-aware lookup dict. No helper method. Just bump the number.

### `llm_base.py` — `_sync_generate` (~line 604)

```python
# Before:
"max_tokens": 8192,

# After:
"max_tokens": 16384,
```

### `llm_base.py` — `_sync_generate_json` (~line 617)

Same change.

## Scope

- **1 file changed**: `llm_base.py`
- **2 lines changed** (one number each)
