# Phase 2: Integration into seed_defaults.py

## Single File Change

The only file modified is `backend/app/services/seed_defaults.py`.

## What to Do

Append 4 new dicts to the `KAIRA_BOT_EVALUATORS` list (currently at line 652). The list currently has 4 entries. After this change, it will have 8.

Each new dict uses the exact same key structure as the existing 4:

```python
{
    "app_id": "kaira-bot",
    "name": "<evaluator name>",
    "is_global": True,
    "listing_id": None,
    "show_in_header": <True or False>,
    "prompt": """<prompt text with {{chat_transcript}}>""",
    "output_schema": [<field dicts>],
}
```

## Insertion Point

After the closing `}` of the "Risk Detection" evaluator (currently line 1000) and before the closing `]` of `KAIRA_BOT_EVALUATORS` (currently line 1001).

## New Entries (in order)

1. **Domain Routing Accuracy** — `show_in_header: True`
2. **Data Faithfulness** — `show_in_header: True`
3. **CGM-Food Correlation Quality** — `show_in_header: False`
4. **Date Handling Accuracy** — `show_in_header: False`

Prompts and output_schema dicts are specified verbatim in `PHASE_1_EVALUATOR_DEFINITIONS.md`.

## How Seeding Works (No Changes Needed)

### System-level seed (startup)

`_seed_evaluators()` (line 1857) runs on app startup via `seed_all_defaults()` — **wait, actually it doesn't**. Looking at `seed_all_defaults()` (line 1961), `_seed_evaluators()` is NOT called on startup. The comment at line 1967 says:

```python
# kaira-bot evaluators are NOT auto-seeded; they use the on-demand
# POST /api/evaluators/seed-defaults?appId=kaira-bot endpoint instead
```

So seeding happens via two paths:

### Path 1: On-demand endpoint (primary)

`POST /api/evaluators/seed-defaults?appId=kaira-bot` → `_seed_kaira_bot()` in `evaluators.py` route.

This function:
1. Imports `KAIRA_BOT_EVALUATORS` from `seed_defaults.py`
2. Queries existing evaluators for the calling user (by `tenant_id + user_id + app_id + listing_id=None`)
3. Skips any evaluator whose `name` already exists
4. Creates new evaluators owned by the calling user (NOT system tenant)

**Implication:** When we add 4 new entries to `KAIRA_BOT_EVALUATORS`, any user who calls the seed endpoint again will get the 4 new evaluators created (existing 4 are skipped by name). No changes to the route code needed — the idempotency logic handles it.

### Path 2: System-level seed (startup, currently unused but exists)

`_seed_evaluators()` seeds evaluators as `SYSTEM_TENANT_ID / SYSTEM_USER_ID` with `is_global=True`. It also has update-existing logic (updates `output_schema` of existing evaluators). If this path is ever re-enabled, the 4 new evaluators will be auto-seeded as system globals.

**No changes needed to either seed path.** Both operate on the `KAIRA_BOT_EVALUATORS` list, which is the only thing we're modifying.

## Execution Pipeline (No Changes Needed)

When a user runs one of these evaluators on a kaira-bot chat session:

1. Frontend calls `evaluatorExecutor.executeForSession()` → submits `evaluate-custom` job
2. `custom_evaluator_runner.py` loads the evaluator row from DB
3. `prompt_resolver.resolve_prompt()` finds `{{chat_transcript}}` → calls `format_chat_transcript(messages)` which produces `User: ...\nBot: ...` lines
4. `schema_generator.generate_json_schema(output_schema)` produces JSON Schema from the field definitions
5. LLM is called with the resolved prompt + JSON Schema for structured output
6. `_extract_scores()` finds the `isMainMetric=True` field and puts its value in `summary.overall_score`
7. EvalRun is persisted with full `result` JSON and `summary`

Every step above is existing code, untouched.

## What Could Break (Risk Assessment)

| Risk | Likelihood | Mitigation |
|---|---|---|
| Typo in output_schema key/type | Low | Schema uses only `number`, `boolean`, `text` — the 3 most tested types. Copy structure from existing evaluators. |
| Prompt too long for LLM context | Very low | Existing evaluator prompts are similar length. Chat transcripts are the variable part — already handled. |
| `_extract_scores` can't find main metric | None | Each evaluator has exactly one `isMainMetric: True` field, same as existing. |
| Seed endpoint creates duplicates | None | Idempotency check matches by `name`. Each new evaluator has a unique name. |
| Existing evaluators affected | None | We're appending to the list, not modifying existing entries. |
