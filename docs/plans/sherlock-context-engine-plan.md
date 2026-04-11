# Sherlock Context Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Sherlock's static system prompt with a 4-layer context assembly pipeline that dynamically constructs the LLM payload per turn, enabling multi-tool orchestration, per-app data awareness, and session working memory.

**Architecture:** Four prompt layers (base persona, app context + data profile, user context, session scratchpad) assembled per turn by `assemble_context()` in `chat_handler.py`. No new storage — scratchpad lives in the existing session dict, cross-session memory uses existing tables. Tool loop and adapters unchanged.

**Tech Stack:** Python 3.12 (async SQLAlchemy), React 18 + TypeScript (Zustand, react-markdown, lucide-react), CSS variables from design system.

**Spec:** `docs/plans/sherlock-context-engine-spec.md`

---

## File Map

### New files

| File | Responsibility |
|------|----------------|
| `backend/app/services/chat_engine/prompts/__init__.py` | Package init |
| `backend/app/services/chat_engine/prompts/base.py` | Layer 1: stable persona, orchestration, response format |
| `backend/app/services/chat_engine/prompts/app_context.py` | Layer 2: loads app config + queries fact tables for data profile |
| `backend/app/services/chat_engine/prompts/user_context.py` | Layer 3: loads saved templates + recent tool usage |
| `backend/app/services/chat_engine/prompts/scratchpad.py` | Layer 4: formats session findings/errors/composed report |
| `src/features/chat-widget/ComposedReportCard.tsx` | Inline card showing composed report sections + action buttons |

### Modified files

| File | Change |
|------|--------|
| `backend/app/services/report_builder/session_store.py` | Add scratchpad + context cache fields to `create_session()` |
| `backend/app/services/report_builder/chat_handler.py` | Replace `SYSTEM_PROMPT` with `assemble_context()`, add `_update_scratchpad()`, update streaming variant |
| `backend/app/services/report_builder/schemas.py` | Add `detail` field to `ToolCallOut` |
| `backend/app/routes/report_builder.py` | Pass `detail` from tool_call_log into `ToolCallOut` |
| `src/features/chat-widget/types.ts` | Add `detail` to `ToolCallBadgeData`, add `PromptChipsProps` to `ChatMessagesProps` |
| `src/features/chat-widget/api.ts` | Extend `ChatResponse.toolCalls` with `detail` |
| `src/features/chat-widget/useChatWidget.ts` | Map detail from API response, add retry action |
| `src/features/chat-widget/ChatWidget.tsx` | Wire PromptChips component |
| `src/features/chat-widget/ChatMessages.tsx` | Render ComposedReportCard, copy button, retry button, streaming indicator |
| `src/features/chat-widget/ToolCallBadge.tsx` | Expandable detail view on click |

### Unchanged

| File | Why |
|------|-----|
| `backend/app/services/chat_engine/runner.py` | Tool loop works, no changes needed |
| `backend/app/services/chat_engine/sql_agent.py` | Already hardened with cache/EXPLAIN/retry |
| `backend/app/services/chat_engine/semantic_model.yaml` | Already points at fact tables |
| `backend/app/services/report_builder/tool_definitions.py` | Tools stay the same |
| `backend/app/services/report_builder/tool_handlers.py` | Tool dispatch stays the same |

---

## Task 1: Prompt Layer 1 — Base Persona

**Files:**
- Create: `backend/app/services/chat_engine/prompts/__init__.py`
- Create: `backend/app/services/chat_engine/prompts/base.py`

- [ ] **Step 1: Create prompts package**

```python
# backend/app/services/chat_engine/prompts/__init__.py
```

Empty file. Just establishes the package.

- [ ] **Step 2: Create base.py with Layer 1 prompt**

```python
# backend/app/services/chat_engine/prompts/base.py
"""Layer 1: Stable persona, orchestration rules, response format.

This is the STABLE PREFIX of the system prompt — never changes per app,
user, or turn. Maximizes KV-cache hit rate across requests.
"""

PROMPT = """\
You are Sherlock, an AI analytics assistant for an evaluation platform.
You help users understand their evaluation data and build custom reports.

TOOLS:

1. analyze(question) — For ALL data questions. Generates a database query and returns results.
   Be specific: include what you want to know and any filters.
   Examples:
   - "What is the average result_score for call_rubric evaluations?"
   - "Which criterion_id has the most VIOLATED status?"
   - "Show pass_rate trend from analytics_run_facts ordered by date"

2. Report builder tools — For composing and saving report layouts:
   - list_app_sections(app_id): see what sections are available for this app
   - get_section_detail(section_type): get details about a section type
   - compose_report(report_name, sections): create a report layout
   - save_template(report_name, sections): save a report layout as a reusable template

ORCHESTRATION:
- You can chain tools freely within a single turn. You have up to 5 tool rounds.
- If the user asks to analyze data AND build a report, do both: analyze first
  to understand the data, then compose a report informed by what you learned.
- If the user asks to save a report you just composed, call save_template with
  the sections from your session state.
- If a tool call fails, the error stays in context. Use it to try a different approach.
- If unsure which tool to use, start with analyze. You can always follow up.

RESPONSE FORMAT:
- Lead with the answer. No preamble.
- Markdown tables for tabular data.
- Bold key numbers: **78% pass rate**, **12 failures**.
- Use arrows for comparisons: **+5%**, **-3 threads**.
- Short IDs (first 8 chars of UUIDs).
- Never dump raw JSON or SQL. Format for humans.
- Never explain what tools you are calling. Just call them and present results.
"""


def render() -> str:
    """Return the stable base prompt. Always the same string."""
    return PROMPT
```

- [ ] **Step 3: Verify import**

Run: `docker compose exec backend python -c "from app.services.chat_engine.prompts.base import render; print(len(render()), 'chars')"`

Expected: prints char count, no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_engine/prompts/
git commit -m "feat(sherlock): add Layer 1 base persona prompt module"
```

---

## Task 2: Prompt Layer 2 — App Context + Data Profile

**Files:**
- Create: `backend/app/services/chat_engine/prompts/app_context.py`

- [ ] **Step 1: Create app_context.py**

```python
# backend/app/services/chat_engine/prompts/app_context.py
"""Layer 2: App configuration + data profile from fact tables.

Assembled once when a session starts. Cached in session['_app_context'].
Queries fact tables to build a self-describing data profile — no hardcoded
app names, evaluator types, or field lists.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def render(session: dict[str, Any], db: AsyncSession) -> str:
    """Build Layer 2 context. Cached after first call."""
    cached = session.get("_app_context")
    if cached is not None:
        return cached

    app_id = session["app_id"]
    tenant_id = session["tenant_id"]

    parts = [f"APP CONTEXT ({app_id}):"]

    # Part A: App config — available report sections
    sections_text = await _load_app_sections(app_id, db)
    if sections_text:
        parts.append(sections_text)

    # Part B: Data profile from fact tables
    profile_text = await _load_data_profile(app_id, tenant_id, db)
    if profile_text:
        parts.append(profile_text)

    result = "\n".join(parts)
    session["_app_context"] = result
    return result


async def _load_app_sections(app_id: str, db: AsyncSession) -> str:
    """Load available report sections from App.config."""
    try:
        from app.models.app import App
        from sqlalchemy import select

        row = await db.execute(
            select(App.config).where(App.slug == app_id, App.is_active.is_(True))
        )
        config = row.scalar_one_or_none()
        if not config:
            return ""

        analytics = (config or {}).get("analytics", {})
        single_run = analytics.get("singleRun", {})
        sections = single_run.get("sections", [])
        if not sections:
            return ""

        names = [s.get("type", s.get("key", "")) for s in sections if isinstance(s, dict)]
        if not names:
            return ""

        return f"Available report sections: {', '.join(names)}"
    except Exception as e:
        logger.warning("Failed to load app sections for %s: %s", app_id, e)
        return ""


async def _load_data_profile(app_id: str, tenant_id: str, db: AsyncSession) -> str:
    """Query fact tables to build a self-describing data profile.

    No hardcoding — discovers what evaluator types, context fields,
    criterion sources, and run shapes exist for this app from the data itself.
    """
    try:
        params = {"app_id": app_id, "tenant_id": tenant_id}
        lines = ["DATA PROFILE:"]

        # 1. Evaluator types
        r = await db.execute(text("""
            SELECT evaluator_type, evaluator_name, COUNT(*) as n
            FROM analytics_eval_facts
            WHERE app_id = :app_id AND tenant_id = :tenant_id
            GROUP BY evaluator_type, evaluator_name
            ORDER BY n DESC
        """), params)
        evals = r.all()
        if evals:
            parts = [f"{row[0]}/{row[1]} ({row[2]})" for row in evals]
            lines.append(f"Evaluators: {', '.join(parts)}")
        else:
            lines.append("Evaluators: (no evaluation data yet)")

        # 2. Context fields on eval_facts
        r2 = await db.execute(text("""
            SELECT DISTINCT jsonb_object_keys(context) as field
            FROM analytics_eval_facts
            WHERE app_id = :app_id AND tenant_id = :tenant_id
        """), params)
        fields = [row[0] for row in r2 if row[0]]
        if fields:
            lines.append(f"Context fields on eval_facts: {', '.join(fields)}")
            lines.append(f"  (query with: context->>'field_name')")

        # 3. Criterion sources
        r3 = await db.execute(text("""
            SELECT criterion_source, COUNT(*) as n
            FROM analytics_criterion_facts
            WHERE app_id = :app_id AND tenant_id = :tenant_id
            GROUP BY criterion_source
        """), params)
        criteria = r3.all()
        if criteria:
            parts = [f"{row[0]} ({row[1]} rows)" for row in criteria]
            lines.append(f"Criterion data: {', '.join(parts)}")
        else:
            lines.append("Criterion data: (none — no rule/criterion data for this app)")

        # 4. Run-level shape
        r4 = await db.execute(text("""
            SELECT eval_type, COUNT(*) as runs,
                   ROUND(AVG(thread_count)) as avg_items,
                   bool_or(adversarial_total IS NOT NULL) as has_adversarial
            FROM analytics_run_facts
            WHERE app_id = :app_id AND tenant_id = :tenant_id
            GROUP BY eval_type
        """), params)
        run_types = r4.all()
        if run_types:
            parts = []
            for row in run_types:
                desc = f"{row[0]} ({row[1]} runs, ~{int(row[2] or 0)} items/run"
                if row[3]:
                    desc += ", has adversarial stats"
                desc += ")"
                parts.append(desc)
            lines.append(f"Run types: {', '.join(parts)}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning("Failed to load data profile for %s: %s", app_id, e)
        return ""
```

- [ ] **Step 2: Verify against live data**

Run:
```bash
docker compose exec backend python -c "
import asyncio
from app.database import async_session
from app.services.chat_engine.prompts.app_context import render

async def test():
    for app in ('kaira-bot', 'voice-rx', 'inside-sales'):
        async with async_session() as db:
            session = {'app_id': app, 'tenant_id': 'af2fcf2b-40a7-4b1a-8fb1-6da0bed73383', '_app_context': None}
            result = await render(session, db)
            print(f'=== {app} ===')
            print(result)
            print()

asyncio.run(test())
"
```

Expected: each app shows different evaluator types, context fields, criterion sources. No hardcoded values. kaira-bot has criterion data, voice-rx and inside-sales do not.

- [ ] **Step 3: Verify caching — second call returns cached string**

Run:
```bash
docker compose exec backend python -c "
import asyncio
from app.database import async_session
from app.services.chat_engine.prompts.app_context import render

async def test():
    async with async_session() as db:
        session = {'app_id': 'kaira-bot', 'tenant_id': 'af2fcf2b-40a7-4b1a-8fb1-6da0bed73383', '_app_context': None}
        r1 = await render(session, db)
        r2 = await render(session, db)
        print(f'Same object: {r1 is r2}')  # True — cached

asyncio.run(test())
"
```

Expected: `Same object: True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_engine/prompts/app_context.py
git commit -m "feat(sherlock): add Layer 2 app context + data profile prompt"
```

---

## Task 3: Prompt Layer 3 — User Context

**Files:**
- Create: `backend/app/services/chat_engine/prompts/user_context.py`

- [ ] **Step 1: Create user_context.py**

```python
# backend/app/services/chat_engine/prompts/user_context.py
"""Layer 3: User context — saved templates and recent activity.

Assembled once per session. Cached in session['_user_context'].
Queries report_configs and agent_tool_logs for cross-session memory.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def render(session: dict[str, Any], db: AsyncSession) -> str:
    """Build Layer 3 context. Cached after first call. Returns empty string if no data."""
    cached = session.get("_user_context")
    if cached is not None:
        return cached

    app_id = session["app_id"]
    tenant_id = session["tenant_id"]
    user_id = session["user_id"]
    lines: list[str] = []

    try:
        # Saved report templates
        r = await db.execute(text("""
            SELECT name FROM report_configs
            WHERE tenant_id = :tid AND app_id = :aid
            ORDER BY updated_at DESC LIMIT 5
        """), {"tid": tenant_id, "aid": app_id})
        templates = [row[0] for row in r if row[0]]
        if templates:
            lines.append(f"Saved report templates: {', '.join(repr(t) for t in templates)}")
    except Exception as e:
        logger.debug("Failed to load templates: %s", e)

    try:
        # Recent tool usage (last 7 days)
        r2 = await db.execute(text("""
            SELECT tool_name, COUNT(*) as uses
            FROM agent_tool_logs
            WHERE user_id = :uid AND app_id = :aid
              AND created_at > now() - interval '7 days'
            GROUP BY tool_name ORDER BY uses DESC LIMIT 5
        """), {"uid": user_id, "aid": app_id})
        usage = r2.all()
        if usage:
            parts = [f"{row[0]} ({row[1]} uses)" for row in usage]
            lines.append(f"Recent activity: {', '.join(parts)}")
    except Exception as e:
        logger.debug("Failed to load tool usage: %s", e)

    result = ""
    if lines:
        result = "USER CONTEXT:\n" + "\n".join(lines)

    session["_user_context"] = result
    return result
```

- [ ] **Step 2: Verify import**

Run: `docker compose exec backend python -c "from app.services.chat_engine.prompts.user_context import render; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat_engine/prompts/user_context.py
git commit -m "feat(sherlock): add Layer 3 user context prompt (templates + patterns)"
```

---

## Task 4: Prompt Layer 4 — Session Scratchpad

**Files:**
- Create: `backend/app/services/chat_engine/prompts/scratchpad.py`

- [ ] **Step 1: Create scratchpad.py**

```python
# backend/app/services/chat_engine/prompts/scratchpad.py
"""Layer 4: Session scratchpad — findings, composed report, errors.

Re-rendered every turn (not cached). Injected at the END of the system
prompt to push accumulated knowledge into the model's recency window.
"""
from __future__ import annotations

from typing import Any

# Max findings to include (avoid context bloat on long conversations)
_MAX_FINDINGS = 15
_MAX_ERRORS = 5


def render(session: dict[str, Any]) -> str:
    """Format the session scratchpad for injection into the system prompt."""
    pad = session.get("scratchpad")
    if not pad:
        return ""

    findings = pad.get("findings", [])
    composed = pad.get("composed_report")
    errors = pad.get("errors", [])

    if not findings and not composed and not errors:
        return ""

    lines = ["SESSION STATE:"]

    if findings:
        lines.append("Findings so far:")
        for f in findings[-_MAX_FINDINGS:]:
            lines.append(f"- {f}")

    if composed:
        name = composed.get("name", "Untitled")
        sections = composed.get("sections", [])
        lines.append(f"Current composed report: \"{name}\" ({', '.join(sections)})")

    if errors:
        lines.append("Recent errors:")
        for e in errors[-_MAX_ERRORS:]:
            lines.append(f"- {e}")

    return "\n".join(lines)
```

- [ ] **Step 2: Unit test the formatter**

```bash
docker compose exec backend python -c "
from app.services.chat_engine.prompts.scratchpad import render

# Empty
assert render({}) == ''
assert render({'scratchpad': {'findings': [], 'composed_report': None, 'errors': []}}) == ''

# With findings
session = {'scratchpad': {'findings': ['Pass rate: 51%', 'Top rule: X'], 'composed_report': None, 'errors': []}}
out = render(session)
assert 'Pass rate: 51%' in out
assert 'SESSION STATE:' in out
print('All scratchpad tests pass')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat_engine/prompts/scratchpad.py
git commit -m "feat(sherlock): add Layer 4 session scratchpad prompt"
```

---

## Task 5: Session Store — Add Scratchpad Fields

**Files:**
- Modify: `backend/app/services/report_builder/session_store.py`

- [ ] **Step 1: Update create_session to include scratchpad and context caches**

In `session_store.py`, add three new fields to the session dict created on line 20-27:

```python
# Add after "messages": []
"scratchpad": {"findings": [], "composed_report": None, "errors": []},
"_app_context": None,
"_user_context": None,
```

The full session dict becomes:
```python
session: dict[str, Any] = {
    "app_id": app_id,
    "tenant_id": tenant_id,
    "user_id": user_id,
    "provider": provider,
    "model": model,
    "messages": [],
    "scratchpad": {"findings": [], "composed_report": None, "errors": []},
    "_app_context": None,
    "_user_context": None,
}
```

- [ ] **Step 2: Verify**

Run: `docker compose exec backend python -c "from app.services.report_builder.session_store import create_session; sid, s = create_session('test', 'tid', 'uid', 'gemini', 'flash'); print(s.keys()); print(s['scratchpad'])"`

Expected: dict_keys includes `scratchpad`, `_app_context`, `_user_context`. Scratchpad has empty findings/errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/report_builder/session_store.py
git commit -m "feat(sherlock): add scratchpad + context cache to session store"
```

---

## Task 6: Chat Handler — Context Assembly + Scratchpad Updates

**Files:**
- Modify: `backend/app/services/report_builder/chat_handler.py`

This is the core integration. Replace the static `SYSTEM_PROMPT` with dynamic `assemble_context()` and add `_update_scratchpad()` after each tool dispatch.

- [ ] **Step 1: Add assemble_context function**

Add after the existing imports at the top of `chat_handler.py`:

```python
async def assemble_context(session: dict, db: AsyncSession) -> str:
    """Build the full system prompt from 4 layered prompt modules."""
    from app.services.chat_engine.prompts import base, app_context, user_context, scratchpad

    parts = [
        base.render(),
        await app_context.render(session, db),
        await user_context.render(session, db),
        scratchpad.render(session),
    ]
    return "\n\n".join(p for p in parts if p)
```

- [ ] **Step 2: Add _update_scratchpad function**

Add after `assemble_context`:

```python
def _update_scratchpad(session: dict, tool_name: str, result_str: str) -> None:
    """Update session scratchpad based on tool result."""
    pad = session.get("scratchpad")
    if not pad:
        return
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

- [ ] **Step 3: Delete the SYSTEM_PROMPT constant**

Remove the entire `SYSTEM_PROMPT = """\..."""` block (lines 20-53 in the current file). It's replaced by `assemble_context()`.

- [ ] **Step 4: Update run_chat_turn to use dynamic context + scratchpad**

Replace the line:
```python
    text, session["messages"] = await run_tool_loop(
        ...
        system=SYSTEM_PROMPT,
        ...
    )
```

With:
```python
    # Dynamic context assembly
    system = await assemble_context(session, db)

    ...

    text, session["messages"] = await run_tool_loop(
        ...
        system=system,
        ...
    )
```

And in the `dispatch` callback, add `_update_scratchpad(session, name, result_str)` right after the `dispatch_tool_call` line:

```python
    async def dispatch(name: str, arguments: dict) -> str:
        nonlocal composed_report

        result_str = await dispatch_tool_call(
            name, arguments,
            db=db, auth=auth, app_id=session["app_id"],
        )

        _update_scratchpad(session, name, result_str)   # <-- NEW

        # ... rest unchanged
```

- [ ] **Step 5: Update run_chat_turn_streaming with the same changes**

Apply the same two changes to `run_chat_turn_streaming`:
1. Replace `system=SYSTEM_PROMPT` with `system = await assemble_context(session, db)` before the tool loop
2. Add `_update_scratchpad(session, name, result_str)` in the streaming `dispatch` callback

- [ ] **Step 6: Verify the handler still works end-to-end**

Run the same chat test from the E2E investigation:
```bash
TOKEN=$(docker compose exec -T backend python -c "from app.auth.utils import create_access_token; import uuid; print(create_access_token(user_id=uuid.UUID('44a3afdf-78f8-4789-9f1f-96184359439a'), tenant_id=uuid.UUID('af2fcf2b-40a7-4b1a-8fb1-6da0bed73383'), email='pareekshith.bompally@tatvacare.in', role_id=uuid.UUID('2f0360c3-08b7-42e6-bd5f-d6c4dd8f3b84')))" | tr -d '\r\n')

curl -s -X POST http://localhost:8721/api/report-builder/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"appId":"kaira-bot","sessionId":null,"message":"What is the pass rate?","provider":"gemini","model":"gemini-2.0-flash"}' | python3 -m json.tool
```

Expected: response with `toolCalls: [{name: "analyze", ...}]`, meaningful content, no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/report_builder/chat_handler.py
git commit -m "feat(sherlock): replace static prompt with 4-layer context assembly"
```

---

## Task 7: Backend — Extend ToolCallOut with Detail

**Files:**
- Modify: `backend/app/services/report_builder/schemas.py`
- Modify: `backend/app/services/report_builder/chat_handler.py`
- Modify: `backend/app/routes/report_builder.py`

- [ ] **Step 1: Add detail field to ToolCallOut schema**

In `schemas.py`, update `ToolCallOut`:

```python
class ToolCallOut(CamelModel):
    name: str
    summary: str
    detail: dict | None = None
```

- [ ] **Step 2: Capture detail in chat_handler dispatch callback**

In `chat_handler.py`'s `dispatch` function inside `run_chat_turn`, change the tool_call_log append to include detail:

```python
        summary = _summarize_tool_result(name, result_str)
        # Extract detail for frontend tool badge expansion
        detail = _extract_tool_detail(name, result_str)
        tool_call_log.append({"name": name, "summary": summary, "detail": detail})
```

Add the `_extract_tool_detail` function:

```python
def _extract_tool_detail(name: str, result_str: str) -> dict | None:
    """Extract displayable detail from a tool result for the frontend."""
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return None

    if name == "analyze":
        return {
            "sql": data.get("sql_used"),
            "rowCount": data.get("row_count"),
            "cacheHit": data.get("cache_hit", False),
        }
    return None
```

Apply the same change to the streaming `dispatch` callback in `run_chat_turn_streaming`.

- [ ] **Step 3: Pass detail through in the route handler**

In `report_builder.py`, update the ToolCallOut construction:

```python
        tool_calls=[
            ToolCallOut(name=tc["name"], summary=tc["summary"], detail=tc.get("detail"))
            for tc in result.get("tool_calls", [])
        ],
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/report_builder/schemas.py backend/app/services/report_builder/chat_handler.py backend/app/routes/report_builder.py
git commit -m "feat(sherlock): add tool call detail to API response"
```

---

## Task 8: Frontend — Wire PromptChips

**Files:**
- Modify: `src/features/chat-widget/ChatWidget.tsx`
- Modify: `src/features/chat-widget/ChatMessages.tsx`
- Modify: `src/features/chat-widget/types.ts`

- [ ] **Step 1: Add promptTemplates and onPromptSelect to ChatMessagesProps**

In `types.ts`, the `PromptTemplate` type already exists. No changes to types.ts needed.

In `ChatMessages.tsx`, update the props interface:

```typescript
interface ChatMessagesProps {
  messages: WidgetMessage[];
  status: 'idle' | 'sending' | 'error';
  promptTemplates: PromptTemplate[];
  onPromptSelect: (prompt: string) => void;
}
```

- [ ] **Step 2: Import and render PromptChips in ChatMessages**

In `ChatMessages.tsx`, add import:
```typescript
import { PromptChips } from './PromptChips';
import type { PromptTemplate } from './types';
```

Render PromptChips when messages are empty, inside the empty-state block after the existing `<p>` tag:

```tsx
{messages.length === 0 && (
  <div className="flex flex-col items-center justify-center h-full text-center px-4">
    <img src="/sherlock-icon.svg" alt="Sherlock" className="h-12 w-12 opacity-30 dark:invert mb-3" />
    <p className="text-sm text-[var(--text-muted)] max-w-[280px] leading-relaxed mb-4">
      Ask me to build reports, explore data, or analyze evaluation results.
    </p>
    <PromptChips templates={promptTemplates} onSelect={onPromptSelect} />
  </div>
)}
```

- [ ] **Step 3: Pass props from ChatWidget**

In `ChatWidget.tsx`, add import:
```typescript
import type { PromptTemplate } from './types';
```

Extract templates from chatConfig (already available on line 32):
```typescript
const promptTemplates: PromptTemplate[] = chatConfig.promptTemplates ?? [];
```

Update the `ChatMessages` usage:
```tsx
<ChatMessages
  messages={messages}
  status={status}
  promptTemplates={promptTemplates}
  onPromptSelect={handleSend}
/>
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `npx tsc --noEmit 2>&1 | grep -i "ChatMessages\|PromptChips\|ChatWidget" | head -5`

Expected: no errors related to these components.

- [ ] **Step 5: Commit**

```bash
git add src/features/chat-widget/ChatWidget.tsx src/features/chat-widget/ChatMessages.tsx
git commit -m "feat(sherlock): wire PromptChips into chat widget"
```

---

## Task 9: Frontend — Composed Report Card

**Files:**
- Create: `src/features/chat-widget/ComposedReportCard.tsx`
- Modify: `src/features/chat-widget/ChatMessages.tsx`

- [ ] **Step 1: Create ComposedReportCard component**

```tsx
// src/features/chat-widget/ComposedReportCard.tsx
import { FileText, Save } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { ComposedReport } from '@/features/reportBuilder/types';

interface ComposedReportCardProps {
  report: ComposedReport;
  onSaveTemplate: (name: string) => void;
}

export function ComposedReportCard({ report, onSaveTemplate }: ComposedReportCardProps) {
  return (
    <div className={cn(
      'mt-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-3',
    )}>
      <div className="flex items-center gap-2 mb-2">
        <FileText className="h-3.5 w-3.5 text-[var(--color-brand-primary)]" />
        <span className="text-xs font-semibold text-[var(--text-primary)]">
          {report.reportName}
        </span>
      </div>

      <div className="flex flex-wrap gap-1 mb-2.5">
        {report.sections.map((s) => (
          <span
            key={s.id}
            className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border-subtle)]"
          >
            {s.title}
          </span>
        ))}
      </div>

      <button
        onClick={() => onSaveTemplate(report.reportName)}
        className={cn(
          'flex items-center gap-1.5 text-[11px] font-medium',
          'text-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary-hover)]',
          'transition-colors',
        )}
      >
        <Save className="h-3 w-3" />
        Save as template
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Render in ChatMessages**

In `ChatMessages.tsx`, add import:
```typescript
import { ComposedReportCard } from './ComposedReportCard';
```

After the markdown content block (after `</div>` for prose div, around line 83), add:

```tsx
{msg.composedReport && (
  <ComposedReportCard
    report={msg.composedReport}
    onSaveTemplate={(name) => onPromptSelect(`Save this report as a template called "${name}"`)}
  />
)}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit 2>&1 | grep -i "ComposedReport\|ChatMessages" | head -5`

- [ ] **Step 4: Commit**

```bash
git add src/features/chat-widget/ComposedReportCard.tsx src/features/chat-widget/ChatMessages.tsx
git commit -m "feat(sherlock): add composed report inline card with save button"
```

---

## Task 10: Frontend — Streaming Tool Indicator

**Files:**
- Modify: `src/features/chat-widget/ChatMessages.tsx`
- Modify: `src/features/chat-widget/useChatWidget.ts`

- [ ] **Step 1: Use activeToolCall in ChatMessages**

The store already has `activeToolCall: string | null`. In `ChatMessages.tsx`, read it:

Update the props to include `activeToolCall`:
```typescript
interface ChatMessagesProps {
  messages: WidgetMessage[];
  status: 'idle' | 'sending' | 'error';
  promptTemplates: PromptTemplate[];
  onPromptSelect: (prompt: string) => void;
  activeToolCall: string | null;
}
```

Replace the "Thinking..." indicator:

```tsx
{msg.status === 'streaming' && !msg.content && msg.toolCalls.length === 0 && (
  <span className="flex items-center gap-1.5 text-[var(--text-muted)]">
    <Loader2 className="h-3 w-3 animate-spin" />
    {activeToolCall ? _toolLabel(activeToolCall) : 'Thinking\u2026'}
  </span>
)}
```

Add the label function at module level:

```typescript
const _TOOL_LABELS: Record<string, string> = {
  analyze: 'Querying database\u2026',
  compose_report: 'Composing report\u2026',
  save_template: 'Saving template\u2026',
  list_app_sections: 'Loading sections\u2026',
  list_section_types: 'Loading section types\u2026',
  get_section_detail: 'Loading details\u2026',
};

function _toolLabel(name: string): string {
  return _TOOL_LABELS[name] ?? `Running ${name}\u2026`;
}
```

- [ ] **Step 2: Pass activeToolCall from ChatWidget**

In `ChatWidget.tsx`, read from store:
```typescript
const activeToolCall = useChatWidgetStore((s) => s.activeToolCall);
```

Pass to ChatMessages:
```tsx
<ChatMessages
  messages={messages}
  status={status}
  promptTemplates={promptTemplates}
  onPromptSelect={handleSend}
  activeToolCall={activeToolCall}
/>
```

- [ ] **Step 3: Commit**

```bash
git add src/features/chat-widget/ChatMessages.tsx src/features/chat-widget/ChatWidget.tsx
git commit -m "feat(sherlock): show tool name during streaming instead of Thinking"
```

---

## Task 11: Frontend — Copy Button + Retry Button

**Files:**
- Modify: `src/features/chat-widget/ChatMessages.tsx`

- [ ] **Step 1: Add copy button to assistant messages**

Import icons:
```typescript
import { Loader2, Copy, Check, RotateCcw } from 'lucide-react';
```

Add state for copy feedback at the top of the `ChatMessages` component:
```typescript
const [copiedId, setCopiedId] = useState<string | null>(null);
```

Add import for `useState`:
```typescript
import { useRef, useEffect, useState } from 'react';
```

After the prose `</div>` in the assistant message block, add a copy button:

```tsx
{msg.role === 'assistant' && msg.content && msg.status === 'complete' && (
  <button
    onClick={() => {
      void navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId(null), 1500);
    }}
    className="mt-1 flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
    title="Copy"
  >
    {copiedId === msg.id ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
    {copiedId === msg.id ? 'Copied' : 'Copy'}
  </button>
)}
```

- [ ] **Step 2: Add retry button on error messages**

After the copy button block, add:

```tsx
{msg.status === 'error' && (
  <button
    onClick={() => {
      // Find the last user message before this error and re-send
      const idx = messages.indexOf(msg);
      const lastUserMsg = messages.slice(0, idx).reverse().find((m) => m.role === 'user');
      if (lastUserMsg) onPromptSelect(lastUserMsg.content);
    }}
    className="mt-1.5 flex items-center gap-1 text-[11px] font-medium text-[var(--color-verdict-fail)] hover:text-[var(--text-primary)] transition-colors"
  >
    <RotateCcw className="h-3 w-3" />
    Retry
  </button>
)}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add src/features/chat-widget/ChatMessages.tsx
git commit -m "feat(sherlock): add copy button and retry button to chat messages"
```

---

## Task 12: Frontend — Expandable Tool Badge

**Files:**
- Modify: `src/features/chat-widget/types.ts`
- Modify: `src/features/chat-widget/api.ts`
- Modify: `src/features/chat-widget/useChatWidget.ts`
- Modify: `src/features/chat-widget/ToolCallBadge.tsx`

- [ ] **Step 1: Extend types**

In `types.ts`, update `ToolCallBadgeData`:

```typescript
export interface ToolCallBadgeData {
  name: string;
  summary?: string;
  status: 'running' | 'done';
  detail?: {
    sql?: string;
    rowCount?: number;
    cacheHit?: boolean;
  } | null;
}
```

- [ ] **Step 2: Extend API response type**

In `api.ts`, update the `ChatResponse` interface:

```typescript
interface ChatResponse {
  sessionId: string;
  role: string;
  content: string;
  toolCalls: Array<{ name: string; summary: string; detail?: Record<string, unknown> | null }>;
  composedReport: ComposedReport | null;
}
```

- [ ] **Step 3: Map detail in useChatWidget send()**

In `useChatWidget.ts`, update the toolCalls mapping (around line 195):

```typescript
      const toolCalls = response.toolCalls.map((tc) => ({
        name: tc.name,
        summary: tc.summary,
        status: 'done' as const,
        detail: tc.detail ?? null,
      }));
```

Also update the `selectSession` mapping (around line 113) to include detail:

```typescript
        toolCalls: ((m.metadata as any)?.toolCalls ?? []).map((tc: any) => ({
          name: tc.name,
          summary: tc.summary,
          status: 'done' as const,
          detail: tc.detail ?? null,
        })),
```

- [ ] **Step 4: Make ToolCallBadge expandable**

Replace `ToolCallBadge.tsx`:

```tsx
import { useState } from 'react';
import { cn } from '@/utils/cn';
import { Check, ChevronDown, ChevronUp } from 'lucide-react';
import type { ToolCallBadgeData } from './types';

export function ToolCallBadge({ name, summary, status, detail }: ToolCallBadgeData) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = detail && Object.keys(detail).length > 0;

  return (
    <span className="inline-flex flex-col">
      <button
        onClick={hasDetail ? () => setExpanded((e) => !e) : undefined}
        className={cn(
          'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono font-medium',
          'bg-[var(--color-brand-accent)] text-[var(--color-brand-primary)]',
          hasDetail && 'cursor-pointer hover:brightness-95',
        )}
      >
        {status === 'running' ? (
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-brand-primary)] animate-pulse" />
        ) : (
          <Check className="h-2.5 w-2.5" />
        )}
        {name}
        {summary && <span className="text-[var(--text-muted)]">&middot; {summary}</span>}
        {status === 'running' && <span className="text-[var(--text-muted)]">running&hellip;</span>}
        {hasDetail && (
          expanded
            ? <ChevronUp className="h-2.5 w-2.5 ml-0.5" />
            : <ChevronDown className="h-2.5 w-2.5 ml-0.5" />
        )}
      </button>
      {expanded && detail && (
        <span className="mt-1 px-2 py-1 rounded bg-[var(--bg-secondary)] text-[9px] font-mono text-[var(--text-muted)] leading-relaxed max-w-[280px] break-all">
          {detail.sql && <span className="block">SQL: {detail.sql}</span>}
          {detail.rowCount != null && <span className="block">Rows: {detail.rowCount}</span>}
          {detail.cacheHit && <span className="block">Cache: hit</span>}
        </span>
      )}
    </span>
  );
}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `npx tsc --noEmit`

- [ ] **Step 6: Commit**

```bash
git add src/features/chat-widget/types.ts src/features/chat-widget/api.ts src/features/chat-widget/useChatWidget.ts src/features/chat-widget/ToolCallBadge.tsx
git commit -m "feat(sherlock): expandable tool call badges with SQL detail"
```

---

## Task 13: Integration Test — Full E2E

- [ ] **Step 1: Rebuild backend**

```bash
docker compose up --build -d backend
```

- [ ] **Step 2: Run 3-app test**

Test each app with the Sherlock endpoint. Generate a token and run:

```bash
# kaira-bot: should use correctness/efficiency/intent evaluators
curl -s POST .../chat -d '{"appId":"kaira-bot","message":"What is the pass rate?","provider":"gemini","model":"gemini-2.0-flash",...}'

# voice-rx: should use critique evaluator, NOT pass_rate
curl -s POST .../chat -d '{"appId":"voice-rx","message":"How did the latest transcription score?","provider":"gemini","model":"gemini-2.0-flash",...}'

# inside-sales: should use context->>'agent', result_score
curl -s POST .../chat -d '{"appId":"inside-sales","message":"Which agent scores lowest?","provider":"gemini","model":"gemini-2.0-flash",...}'
```

Verify:
- Each app returns meaningful data (not empty results)
- agent_tool_logs shows correct generated_sql for each
- No hardcoded app names in generated SQL

- [ ] **Step 3: Test multi-tool chain**

```bash
curl -s POST .../chat -d '{"appId":"kaira-bot","message":"Analyze the pass rate and then build me a report with rule compliance and exemplar threads","provider":"gemini","model":"gemini-2.0-flash",...}'
```

Verify response has BOTH analyze and compose_report in toolCalls.

- [ ] **Step 4: Test scratchpad carry-over**

Send two messages in the same session:
1. "What is the pass rate?" → get sessionId
2. "Save this as a report template called My Template" → use same sessionId

Verify the second turn uses compose_report or save_template (the LLM knows what data it found because the scratchpad carries findings).

- [ ] **Step 5: Verify frontend builds**

Run: `npx tsc --noEmit && npm run build`

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat(sherlock): context engine integration verified across all 3 apps"
```

---

## Post-Implementation Checklist

- [ ] All 4 prompt layers render correctly (base, app_context, user_context, scratchpad)
- [ ] Data profile auto-discovers evaluator types per app (no hardcoding)
- [ ] voice-rx queries use `evaluator_type='critique'`, not `pass_rate`
- [ ] inside-sales queries use `context->>'agent'` and `result_score`
- [ ] Multi-tool chains work (analyze → compose_report in one turn)
- [ ] Scratchpad accumulates findings across turns
- [ ] Error retention: failed tool calls appear in scratchpad
- [ ] PromptChips render on empty chat
- [ ] Composed report card renders with section pills + save button
- [ ] Streaming shows tool name ("Querying database...") not "Thinking..."
- [ ] Copy button works on assistant messages
- [ ] Retry button appears on error messages
- [ ] Tool badge expands to show SQL detail
- [ ] `npx tsc --noEmit` passes
- [ ] `npm run build` passes
- [ ] No hardcoded app names anywhere in new code
