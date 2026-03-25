# Kaira Agent Capability Evaluators

## Context

Three new microservices power Kaira Bot's CGM + Food capabilities:

| Service | Repo | What It Does |
|---|---|---|
| **cgm_x_food_agent** | `DHSPL-Tatvacare/cgm_x_food_agent` | Unified agent — correlates glucose data (MongoDB) with food logs (Tatva API) to answer mixed health questions |
| **cgm-agent** | `DHSPL-Tatvacare/cgm-agent` | NL-to-MongoDB query agent for CGM spike and AI insight data, with multi-layer safety guardrails |
| **context-switcher** | `DHSPL-Tatvacare/context-switcher` | Routes user messages to the correct agent (FoodAgent / FoodInsightAgent / CgmAgent / General) and detects topic switches |

These services sit behind the Kaira Bot orchestrator. From the eval platform's perspective, the user still has a chat session with Kaira — the transcript contains User/Bot message pairs. The new capabilities surface as **new types of bot responses** (glucose data, food correlations, routing decisions) that the existing 4 evaluators (Chat Quality, Health Accuracy, Empathy, Risk Detection) were not designed to judge.

## What We're Adding

4 new seeded system evaluators for `app_id="kaira-bot"`. They follow the **exact same pattern** as the existing 4: a prompt with `{{chat_transcript}}`, an `output_schema` array, seeded into `KAIRA_BOT_EVALUATORS` in `seed_defaults.py`.

| # | Evaluator Name | Judges What |
|---|---|---|
| 1 | **Domain Routing Accuracy** | Whether the bot responded in the correct domain given what the user asked |
| 2 | **Data Faithfulness** | Whether the bot's response is grounded in data it presented — no hallucinated numbers, no contradictions |
| 3 | **CGM-Food Correlation Quality** | Whether mixed glucose+food questions got properly correlated answers (not one-sided) |
| 4 | **Date Handling Accuracy** | Whether the bot responded with data for the time period the user actually asked about |

## What We're NOT Adding

- No new `eval_type` values
- No new job handlers or runner code
- No new DB tables or migrations
- No new frontend components
- No new variables in `variable_registry.py`
- No changes to `prompt_resolver.py`, `schema_generator.py`, `custom_evaluator_runner.py`
- No changes to `llm_base.py` or any provider code

## How It Works (Existing Infrastructure, Zero Changes)

```
User clicks "Run Evaluator" on a kaira-bot chat session
  → evaluate-custom job submitted (existing)
  → custom_evaluator_runner loads evaluator prompt + output_schema (existing)
  → prompt_resolver substitutes {{chat_transcript}} with User/Bot text (existing)
  → schema_generator converts output_schema to JSON Schema (existing)
  → LLM judge produces structured JSON matching the schema (existing)
  → _extract_scores pulls isMainMetric field into summary (existing)
  → EvalRun record persisted with result + summary (existing)
  → UI displays scores in header/card layout (existing)
```

The only file that changes is `seed_defaults.py` — appending 4 new dicts to the `KAIRA_BOT_EVALUATORS` list.

## Separation of Concerns

These evaluators judge **observable bot behavior in the transcript**. They do NOT test:
- Internal tool calls (query generation, MongoDB queries) — invisible to the transcript
- Internal routing decisions (context-switcher JSON) — invisible to the transcript
- Internal date parsing (structured JSON output) — invisible to the transcript

Instead, they test the **downstream effect** of those internals:
- Bad routing → bot responds about food when user asked about glucose → Domain Routing catches it
- Bad query → bot returns wrong data → Data Faithfulness catches it
- Bad date parsing → bot returns wrong time period → Date Handling catches it
- Missing correlation → bot answers only one side of a mixed question → CGM-Food Correlation catches it

## Phases

This is a single-phase change. The plan is broken into steps for clarity, not for phased delivery.

| Step | What | File |
|---|---|---|
| 1 | Write 4 evaluator prompt+schema definitions | `PHASE_1_EVALUATOR_DEFINITIONS.md` |
| 2 | Integration into seed_defaults.py | `PHASE_2_INTEGRATION.md` |
| 3 | Verification | `PHASE_3_VERIFICATION.md` |
