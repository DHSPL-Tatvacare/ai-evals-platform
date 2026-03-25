# LLM Factory & App-ID Settings Resolution — Fix Plan

## Problem Statement

Report narrative generation silently fails for all non-Gemini LLM providers
(Anthropic, OpenAI, Azure OpenAI).

**Root cause:** LLM settings (API keys) are stored in the DB at global scope
(`app_id = ''`). There is no per-app LLM configuration — it's not a feature.
But 3 callers in the report generation path pass `app_id=run.app_id`
(e.g. `'kaira-bot'`) when looking up settings. The query becomes
`WHERE app_id = 'kaira-bot'`, finds nothing, and throws `RuntimeError`.

Gemini survives by accident: the `except RuntimeError` fallback constructs
a settings dict with `api_key=""` but a valid `service_account_path`, which
is enough for Gemini's SA auth. Every other provider gets an empty key and
fails silently.

## Evidence (from live system)

**Backend logs (repeated):**
```
Report narrative generation failed: "Could not resolve authentication method.
Expected either api_key or auth_token to be set."
```

**Database state:**
- `llm-settings` exists at `app_id = ''` (global) — contains valid `anthropicApiKey`
- `llm-settings` at `app_id = 'kaira-bot'` — **0 rows**
- All eval runs have `app_id = 'kaira-bot'`

## Architecture Context

All evaluation and report LLM calls run on the **backend** via the jobs system
(`job_worker.py` → registered handlers → `settings_helper` → `create_llm_provider`).
Frontend submits a job, polls for completion, and resumes polling after page refresh.
No LLM call in the eval/report path runs from the browser.

The only frontend-direct LLM calls are prompt/schema generators in Settings —
short-running, Gemini-only, API-key-required. These are unrelated to this fix.

**Gemini auth priority (by design, working correctly):**
- `managed_job` intent: SA preferred, API key fallback
- `interactive` intent: API key preferred, SA fallback
- Non-Gemini providers: API key only, no SA path

`settings_helper.py` implements this correctly. The bug is purely in the
callers passing the wrong `app_id`.

## Fixes

| # | Title | Severity | Files |
|---|-------|----------|-------|
| 1 | [Remove wrong app_id from report callers](./FIX_1_REMOVE_APPID.md) | CRITICAL | `report_service.py`, `routes/reports.py` |
| 2 | [Make RuntimeError fallback provider-aware](./FIX_2_FALLBACK_GUARD.md) | HIGH | `report_service.py` |
| 3 | [Add missing provider_override to custom eval narrative](./FIX_3_CUSTOM_EVAL_OVERRIDE.md) | HIGH | `report_service.py` |
| 4 | [Add provider_override to model discovery](./FIX_4_DISCOVERY_KEY.md) | MEDIUM | `routes/llm.py` |
| 5 | [Bump Anthropic max_tokens](./FIX_5_ANTHROPIC_MAX_TOKENS.md) | MEDIUM | `llm_base.py` |

## Execution Order

Fix 1 is the core fix. Fixes 2-5 are independent of each other and can be
done in any order after Fix 1. All 5 can be done in a single commit.

## Files Touched (complete list)

| File | Fixes |
|------|-------|
| `backend/app/services/reports/report_service.py` | 1, 2, 3 |
| `backend/app/routes/reports.py` | 1 |
| `backend/app/routes/llm.py` | 4 |
| `backend/app/services/evaluators/llm_base.py` | 5 |

4 files, ~19 lines changed. No schema changes. No frontend changes.
No new abstractions.

## What Was Removed From the Original Plan

- **Phase 1 (3-tier fallback in settings_helper):** Overengineered. LLM settings
  are global — fix the callers, not the lookup function.
- **Phase 5 (narrative_provider metadata + frontend sync):** Scope creep. UI polish,
  not related to the core failure.
- **Phase 6 (model-aware max_tokens dict):** Overengineered. Just bump the constant.
- **Phase 7 (narrative error surfacing to frontend):** Scope creep. Once the core
  fix works, there's nothing to surface. Can be revisited later if needed.
