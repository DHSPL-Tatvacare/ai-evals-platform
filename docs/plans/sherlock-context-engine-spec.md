# Sherlock Context Engine — Design Specification

> Transforms Sherlock from a static-prompt chat assistant into a context-engineered agent
> that dynamically assembles its LLM payload per turn, works across all apps without
> hardcoding, orchestrates multi-tool workflows, and maintains working memory within sessions.

**Date:** 2026-04-11
**References:** Context Engineering (Google, Manus, Weaviate), Google Agent Guide

---

## 1. The Problem

### What exists today

Sherlock is a single-agent chat assistant with 6 tools (analyze, 5 report builder tools) and a static 52-line system prompt. It runs a ReAct tool loop (up to 5 rounds per message) powered by Gemini or OpenAI.

### What breaks

1. **Same prompt for every app.** The system prompt doesn't tell the LLM what data each app has. For kaira-bot (threads, rules, adversarial), it works. For voice-rx (single listings, critique scores, no rules) and inside-sales (calls, agent scores, no rules), the LLM generates SQL against wrong columns because it doesn't know the data shape.

2. **No orchestration.** The system prompt says "use analyze for data, report tools ONLY when explicitly asked." This prevents natural multi-step flows: "analyze the data and build me a report" should chain analyze → compose_report in one turn. The LLM has the capability (5 tool rounds) but the prompt discourages it.

3. **No working memory.** When Sherlock calls `analyze` 3 times in a conversation, by turn 8 the model has lost track of what it learned. The context is polluted with full SQL results from earlier turns. No scratchpad summarizes accumulated findings.

4. **Dead UI components.** PromptChips component exists but is never rendered. composedReport data flows end-to-end but has no UI. Save template works but has no button.

5. **Prompt templates broken.** Hardcoded defaults exist for all 3 apps, App.config can override, but the component is orphaned — never imported into ChatWidget.

---

## 2. The Solution

### Core idea: Context Engineering

Replace the static system prompt with a **4-layer context assembly pipeline** that dynamically constructs the LLM payload every turn. Each layer is a separate module. The system prompt prefix stays stable (KV-cache friendly), dynamic context is appended.

### Architecture

```
USER MESSAGE
    |
    v
+------------------------------------------+
|       CONTEXT ASSEMBLY (per turn)        |
|                                          |
|  Layer 1: Base persona + tool routing    |
|           (STABLE — never changes)       |
|  Layer 2: App context + data profile     |
|           (per session, from DB)         |
|  Layer 3: User context                   |
|           (templates, recent patterns)   |
|  Layer 4: Session scratchpad             |
|           (findings, composed report)    |
+------------------+-----------------------+
                   |
                   v
+------------------------------------------+
|       TOOL LOOP (ReAct, 5 rounds)        |
|  (runner.py — unchanged)                 |
|                                          |
|  LLM reasons -> calls tool -> observes   |
|  -> scratchpad updated -> loop           |
+------------------+-----------------------+
                   |
                   v
+------------------------------------------+
|       RESPONSE + SIDE EFFECTS            |
|                                          |
|  -> Stream to frontend                   |
|  -> Log tool calls (agent_tool_logs)     |
|  -> Update scratchpad in session         |
|  -> Persist messages to chat_messages    |
+------------------------------------------+
```

---

## 3. The Four Context Layers

### Layer 1: Base Persona (stable prefix)

Static text. Never changes per app, user, or turn. Maximizes KV-cache hit rate (Manus principle: keep prompt prefix stable).

Contains:
- Sherlock persona and personality
- Tool routing guidance — but **encouraging orchestration**, not gating it
- Response format rules (markdown tables, bold numbers, no raw JSON)
- Orchestration permission: "You can chain tools freely. If analyzing data reveals something worth reporting, do both."

Lives in: `backend/app/services/chat_engine/prompts/base.py`

Does NOT contain: app-specific details, evaluator names, section lists, user history.

### Layer 2: App Context + Data Profile

Assembled once when a session starts for an app. Cached in the session dict. Two parts:

**Part A — App Config** (from `apps` table):
- Available report sections for this app (from `App.config.analytics.singleRun.sections`)
- App display name and description

**Part B — Data Profile** (from fact tables, self-describing):
Four indexed queries that run once per session:

```sql
-- Evaluator types available
SELECT evaluator_type, evaluator_name, COUNT(*) as n
FROM analytics_eval_facts WHERE app_id = :app_id AND tenant_id = :tenant_id
GROUP BY evaluator_type, evaluator_name

-- Context fields populated (for inside-sales: agent, direction, duration)
SELECT DISTINCT jsonb_object_keys(context) as field
FROM analytics_eval_facts WHERE app_id = :app_id AND tenant_id = :tenant_id

-- Criterion sources (for kaira-bot: rule_catalog)
SELECT criterion_source, COUNT(*) as n
FROM analytics_criterion_facts WHERE app_id = :app_id AND tenant_id = :tenant_id
GROUP BY criterion_source

-- Run-level shape
SELECT eval_type, COUNT(*) as runs,
       ROUND(AVG(thread_count)) as avg_items,
       bool_or(adversarial_total IS NOT NULL) as has_adversarial
FROM analytics_run_facts WHERE app_id = :app_id AND tenant_id = :tenant_id
GROUP BY eval_type
```

The profile is formatted as natural language for the LLM:

For kaira-bot:
```
DATA PROFILE:
Evaluators: intent/Intent Accuracy (5), correctness/Correctness (5),
  efficiency/Efficiency (5), adversarial_judge/Adversarial Judge (65), custom (1)
Context fields on eval_facts: difficulty, total_turns
Criterion data: rule_catalog (correctness + efficiency rules)
Run types: batch_thread (1 run, ~5 threads), batch_adversarial (3 runs, adversarial stats)
```

For voice-rx:
```
DATA PROFILE:
Evaluators: critique/Voice Rx Critique (2), custom (10)
Context fields on eval_facts: (none)
Criterion data: (none — no rule compliance for this app)
Run types: full_evaluation (2 runs, 1 item each), custom (10 runs, 1 item each)
Note: Evaluates individual recordings, not conversation threads.
```

For inside-sales:
```
DATA PROFILE:
Evaluators: call_rubric/Quality Evaluation (10)
Context fields on eval_facts: agent, direction, duration, recording_url
Criterion data: (none)
Run types: call_quality (1 run, ~10 calls)
Note: Scores in result_score. Use context->>'agent' for per-agent analysis.
```

**Why this works for any app:** When a new app `pillup-bot` is added with evaluator type `dosage_check` and context field `medication`, the data profile auto-discovers it. Zero code changes.

Lives in: `backend/app/services/chat_engine/prompts/app_context.py`
Cached in: `session["_app_context"]` (string, built once)

### Layer 3: User Context

Assembled once per session. Two SQL queries against existing tables:

```sql
-- Saved report templates
SELECT name FROM report_configs
WHERE tenant_id = :tid AND app_id = :aid
ORDER BY updated_at DESC LIMIT 5

-- Recent tool usage patterns
SELECT tool_name, COUNT(*) as uses
FROM agent_tool_logs
WHERE user_id = :uid AND app_id = :aid
  AND created_at > now() - interval '7 days'
GROUP BY tool_name ORDER BY uses DESC LIMIT 5
```

Formatted as:
```
USER CONTEXT:
Saved report templates: "Compliance Deep Dive" (3 sections), "Weekly Summary" (5 sections)
Recent activity: analyze (12 uses), compose_report (3 uses)
```

If no templates or recent activity, this layer is omitted (empty string).

Lives in: `backend/app/services/chat_engine/prompts/user_context.py`
Cached in: `session["_user_context"]` (string, built once)

### Layer 4: Session Scratchpad

Updated after every tool call. Injected at the END of the system prompt each turn (Manus recitation principle — push objectives/findings into recency where model attention is strongest).

Structure in session:
```python
session["scratchpad"] = {
    "findings": [],           # accumulated data insights
    "composed_report": None,  # current composed report config
    "errors": [],             # failed tool calls (keep wrong stuff in)
}
```

Updated by `chat_handler.py` after each tool dispatch:
- `analyze` success → append finding summary to `findings`
- `analyze` failure → append error to `errors` (Manus: keep errors in context)
- `compose_report` success → set `composed_report`
- `save_template` success → append to `findings`

Formatted as:
```
SESSION STATE:
Findings so far:
- Overall pass rate: 51.33% across 5 runs
- Most violated rule: single_item_one_table (16.7% compliance)
- Pass rate trend: 73% → 20% → 3% → 60% → 100%

Current composed report: "Compliance Analysis Report" (summary_cards, compliance_table, exemplars)
```

Lives in: `backend/app/services/chat_engine/prompts/scratchpad.py`
Lives in session: `session["scratchpad"]` (dict, updated each turn)

---

## 4. Context Assembly

A single function in `chat_handler.py` replaces the static `SYSTEM_PROMPT` constant:

```python
async def assemble_context(session: dict, db: AsyncSession) -> str:
    """Build the full system prompt from 4 layers."""
    from app.services.chat_engine.prompts import base, app_context, user_context, scratchpad

    parts = [
        base.render(),
        await app_context.render(session, db),
        await user_context.render(session, db),
        scratchpad.render(session),
    ]
    return "\n\n".join(p for p in parts if p)
```

Layers 2 and 3 are cached after first call (stored as strings in the session dict). Layer 4 re-renders every turn. Layer 1 is a constant.

---

## 5. Orchestration

### What changes

The tool loop (`runner.py`) does NOT change. The adapters do NOT change. The tools do NOT change.

Only the **system prompt changes** — Layer 1's orchestration section replaces the rigid routing:

**Before:**
```
ROUTING:
- Data questions → analyze. Always.
- "Build me a report" / "compose" / "save template" → report builder tools.
- If unsure → analyze.
```

**After:**
```
ORCHESTRATION:
- Use analyze for any data question.
- Use report builder tools when the user wants to compose or save a report.
- You can chain tools freely. Examples:
  - User asks "analyze the data and build me a report" → call analyze first,
    then use the results to compose a report.
  - User asks "save this" after composing → call save_template with the
    composed report from your session state.
- If a tool call fails, try a different approach. The error stays in context —
  use it to inform your next action.
- If unsure which tool, start with analyze. You can always follow up.
```

The LLM decides tool order. The 5-round loop gives it room to chain. The scratchpad carries state between tools.

### Error retention

Today: failed SQL is retried silently with the same SQL, or the LLM generates a fix but the original error is discarded from context.

After: failed tool calls stay in the message history (they already do — `runner.py` appends tool results regardless of success/failure). The scratchpad also records errors:

```python
# In chat_handler dispatch callback:
if result.get("status") == "error":
    session["scratchpad"]["errors"].append(
        f"Tool {name} failed: {result.get('error', '')[:200]}"
    )
```

The LLM sees both the error in message history AND the scratchpad summary. Per Manus: "leaving the wrong turns in the context reduces the chance of repeating the same mistake."

---

## 6. Session & Memory Storage

### Scratchpad (working memory)

Lives in the existing session dict in `session_store.py`. No new storage layer.

```python
# session_store.py create_session() adds:
session["scratchpad"] = {"findings": [], "composed_report": None, "errors": []}
session["_app_context"] = None   # cached Layer 2 string
session["_user_context"] = None  # cached Layer 3 string
session["_data_profile"] = None  # cached raw profile data
```

When session expires (1hr TTL), everything dies with it. Correct behavior.

### Cross-session memory

No new storage. Queries against existing tables:
- `report_configs` → saved templates (procedural memory)
- `agent_tool_logs` → recent usage patterns (episodic memory)

Both queried once per session at first turn, cached in session dict.

### What we explicitly do NOT add

- No vector database — data is structured SQL, not unstructured documents
- No graph database — no entity traversal beyond SQL joins
- No embedding pipeline — the semantic model describes the schema
- No external memory service — PostgreSQL is sufficient
- No agent framework (LangGraph, ADK, etc.) — we have our own tool loop that works

---

## 7. Prompt File Organization

```
backend/app/services/chat_engine/prompts/
    __init__.py          # empty
    base.py              # Layer 1: persona, orchestration, response format
    app_context.py       # Layer 2: app config + data profile from fact tables
    user_context.py      # Layer 3: templates + recent patterns
    scratchpad.py        # Layer 4: session findings + composed report + errors
```

Each module exports a `render()` function that returns a string (or empty string if nothing to inject). Pure functions, no side effects, testable in isolation.

`base.py` exports a constant string. The other three take `session` and optionally `db` as args.

---

## 8. Chat Handler Changes

### run_chat_turn() — updated flow

```python
async def run_chat_turn(session, user_message, *, provider, model, db, auth):
    tools = await _resolve_tools_for_app(session["app_id"], db)
    adapter = await create_adapter(provider=provider, model=model, ...)
    session["messages"].append(adapter.build_user_message(user_message))

    # NEW: dynamic context assembly
    system = await assemble_context(session, db)

    composed_report = None
    tool_call_log = []

    async def dispatch(name, arguments):
        nonlocal composed_report
        result_str = await dispatch_tool_call(name, arguments, db=db, auth=auth, app_id=session["app_id"])

        # NEW: update scratchpad
        _update_scratchpad(session, name, result_str)

        # Existing: track composed report
        if name == "compose_report":
            parsed = json.loads(result_str)
            if parsed.get("status") == "ok":
                composed_report = parsed

        if name == "save_template":
            await db.commit()

        summary = _summarize_tool_result(name, result_str)
        tool_call_log.append({"name": name, "summary": summary})
        return result_str

    text, session["messages"] = await run_tool_loop(
        adapter=adapter, messages=session["messages"],
        tools=tools, system=system,       # <-- dynamic, not static
        temperature=0.3, dispatch_fn=dispatch, max_rounds=MAX_TOOL_ROUNDS,
    )
    ...
```

### _update_scratchpad() — new function

```python
def _update_scratchpad(session: dict, tool_name: str, result_str: str) -> None:
    """Update session scratchpad based on tool result."""
    pad = session.setdefault("scratchpad", {"findings": [], "composed_report": None, "errors": []})
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return

    if data.get("status") == "error":
        pad["errors"].append(f"{tool_name}: {data.get('error', '')[:200]}")
        return

    if tool_name == "analyze" and data.get("status") == "ok":
        question = data.get("question", "")
        row_count = data.get("row_count", 0)
        # Keep finding short — just the question + row count
        pad["findings"].append(f"{question} ({row_count} rows)")

    elif tool_name == "compose_report" and data.get("status") == "ok":
        pad["composed_report"] = {
            "name": data.get("report_name"),
            "sections": [s.get("type") for s in data.get("sections", [])],
        }

    elif tool_name == "save_template":
        name = data.get("report_name", "template")
        pad["findings"].append(f"Saved template: {name}")
```

---

## 9. Frontend Changes

### 9.1 Wire PromptChips (fix orphaned component)

`ChatWidget.tsx` already reads `chatConfig.promptTemplates` from `appConfig.chat`. Just import `PromptChips` and render it between `ChatMessages` and `ChatInput`, passing templates and an `onSelect` handler that calls `send()`.

Show only when: messages are empty (first turn), templates exist.

### 9.2 Composed Report Preview

When `msg.composedReport` is not null, render an inline card in `ChatMessages`:

- Section list as pills/chips (type + title)
- "Save as Template" button (triggers send with "Save this report as a template called [name]")
- "Apply to Current Run" button (navigates to report view with this config)

### 9.3 Streaming Tool Indicator

During streaming, when `tool_call_start` SSE event arrives, show the tool name instead of generic "Thinking...":
- analyze → "Querying database..."
- compose_report → "Composing report..."
- save_template → "Saving template..."
- list_app_sections → "Loading sections..."

### 9.4 Copy Button on Messages

Hover action on assistant messages. Copies markdown content to clipboard.

### 9.5 Retry on Error

When `msg.status === 'error'`, show a "Retry" button that re-sends the last user message.

### 9.6 Tool Call Detail Expand

Clicking a tool badge expands to show:
- For analyze: SQL used, execution time, row count, cache hit
- For other tools: execution time

Data source: the tool result is already in `msg.toolCalls` — extend `ToolCallBadgeData` to include `detail` from the tool result.

---

## 10. Files Changed / Created

### New files

| File | Purpose |
|------|---------|
| `backend/app/services/chat_engine/prompts/__init__.py` | Package init |
| `backend/app/services/chat_engine/prompts/base.py` | Layer 1: stable persona + orchestration |
| `backend/app/services/chat_engine/prompts/app_context.py` | Layer 2: app config + data profile |
| `backend/app/services/chat_engine/prompts/user_context.py` | Layer 3: templates + patterns |
| `backend/app/services/chat_engine/prompts/scratchpad.py` | Layer 4: session findings |

### Modified files

| File | Change |
|------|--------|
| `backend/app/services/report_builder/chat_handler.py` | Replace static SYSTEM_PROMPT with `assemble_context()`, add `_update_scratchpad()` |
| `backend/app/services/report_builder/session_store.py` | Add scratchpad + cache fields to `create_session()` |
| `src/features/chat-widget/ChatWidget.tsx` | Wire PromptChips, pass templates |
| `src/features/chat-widget/ChatMessages.tsx` | Render composedReport card, copy button, retry, tool detail expand, streaming indicator |
| `src/features/chat-widget/ToolCallBadge.tsx` | Expandable detail view |
| `src/features/chat-widget/types.ts` | Extend ToolCallBadgeData with detail fields |
| `src/features/chat-widget/useChatWidget.ts` | Pass tool detail from API response into messages |

### Unchanged

- `backend/app/services/chat_engine/runner.py` — tool loop unchanged
- `backend/app/services/chat_engine/sql_agent.py` — unchanged (already hardened)
- `backend/app/services/chat_engine/semantic_model.yaml` — unchanged
- `backend/app/services/report_builder/tool_definitions.py` — unchanged
- `backend/app/services/report_builder/tool_handlers.py` — unchanged
- All eval runners, fact populator, extractors — unchanged

---

## 11. What This Does NOT Do

- Does not add new tools. The 6 existing tools are sufficient.
- Does not change the tool loop or adapter architecture.
- Does not add a vector database, graph database, or embedding pipeline.
- Does not add an agent framework (LangGraph, ADK, etc.).
- Does not hardcode app names, evaluator names, or section types anywhere.
- Does not change the SQL agent or semantic model.
- Does not change the analytics fact tables or extractors.

---

## 12. Success Criteria

### Backend

- [ ] Same 10-turn conversation works for kaira-bot with scratchpad accumulating findings
- [ ] voice-rx "How did the latest transcription score?" generates correct SQL using critique evaluator (not pass_rate)
- [ ] inside-sales "Which agent scores lowest?" generates correct SQL using context->>'agent' and result_score
- [ ] Multi-tool chain works: "analyze the data and build me a report" chains analyze → compose_report in one turn
- [ ] Scratchpad carries composed report from Turn N into Turn N+1 (save template knows what to save)
- [ ] Data profile auto-discovers new evaluator types without code changes
- [ ] Error retention: failed tool call stays in context, LLM adjusts approach

### Frontend

- [ ] PromptChips render on empty chat, disappear after first message
- [ ] Composed report shows inline preview card with section list
- [ ] "Save as Template" button appears after compose_report
- [ ] Streaming shows tool name ("Querying database...") not "Thinking..."
- [ ] Copy button works on assistant messages
- [ ] Retry button appears on error messages
- [ ] Tool badge click expands to show SQL/timing detail
