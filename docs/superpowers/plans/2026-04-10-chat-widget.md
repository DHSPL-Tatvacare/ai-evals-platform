# Floating Chat Widget — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace BuilderOverlay with a floating bottom-right chat widget — simplified provider toggle (Gemini | OpenAI), default models from env vars, ReactMarkdown rendering, tool call badges, prompt chips from App.config, SSE streaming.

**Architecture:** Self-contained `src/features/chat-widget/` feature mounts in MainLayout. Zustand store manages widget state. Backend extended with tool call summaries in response + `/api/chat-engine/defaults` endpoint + SSE streaming endpoint. No `LLMConfigSection` in chat — just two provider pills.

**Tech Stack:** React 18, Zustand, ReactMarkdown + remark-gfm, FastAPI SSE (StreamingResponse), existing chat_engine adapters.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/services/report_builder/schemas.py` | Add `ToolCallOut` to response |
| Modify | `backend/app/services/report_builder/chat_handler.py` | Track tool call summaries |
| Modify | `backend/app/routes/report_builder.py` | Return tool_calls in response, add SSE `/chat/stream` |
| Create | `backend/app/routes/chat_engine.py` | `/api/chat-engine/defaults` endpoint |
| Modify | `backend/app/main.py:262,286` | Register chat_engine router |
| Create | `src/features/chat-widget/types.ts` | Widget message types, store interface |
| Create | `src/features/chat-widget/api.ts` | sendMessage, getDefaults, streamMessage |
| Create | `src/features/chat-widget/useChatWidget.ts` | Zustand store |
| Create | `src/features/chat-widget/ProviderToggle.tsx` | Gemini/OpenAI pills |
| Create | `src/features/chat-widget/PromptChips.tsx` | App.config-driven prompt buttons |
| Create | `src/features/chat-widget/ChatInput.tsx` | Textarea + send button |
| Create | `src/features/chat-widget/ToolCallBadge.tsx` | Tool call inline badge |
| Create | `src/features/chat-widget/ChatMessages.tsx` | Message list with ReactMarkdown |
| Create | `src/features/chat-widget/ChatWidget.tsx` | Floating container (bubble + panel) |
| Modify | `src/components/layout/MainLayout.tsx:78` | Mount `<ChatWidget />` |
| Modify | `src/features/evalRuns/components/report/ReportTab.tsx:12,169,571-581,671-676` | Replace overlay with widget trigger |
| Delete | `src/features/reportBuilder/components/BuilderOverlay.tsx` | Replaced by ChatWidget |

---

### Task 1: Backend — extend schema + track tool calls

**Files:**
- Modify: `backend/app/services/report_builder/schemas.py`
- Modify: `backend/app/services/report_builder/chat_handler.py`
- Modify: `backend/app/routes/report_builder.py`

- [ ] **Step 1: Add ToolCallOut to schemas.py**

Add after the `ComposedReportOut` class in `backend/app/services/report_builder/schemas.py`:

```python
class ToolCallOut(CamelModel):
    name: str
    summary: str
```

Update `BuilderChatResponse` to include tool_calls:

```python
class BuilderChatResponse(CamelModel):
    session_id: str
    role: str = "assistant"
    content: str
    tool_calls: list[ToolCallOut] = []
    composed_report: ComposedReportOut | None = None
```

- [ ] **Step 2: Add tool call tracking + summary helper to chat_handler.py**

Replace `backend/app/services/report_builder/chat_handler.py` with:

```python
"""
Report builder chat surface.
Wires report-specific tools and system prompt into the shared chat engine.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_engine import create_adapter, run_tool_loop
from app.services.report_builder.tool_definitions import TOOLS
from app.services.report_builder.tool_handlers import dispatch_tool_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a report builder assistant. Users describe what they want to see in an \
evaluation report using natural language. Your job is to translate their intent \
into a structured report configuration by selecting and arranging the right \
section types.

WORKFLOW:
1. When the user describes what they want, call list_section_types to see available \
   building blocks.
2. Match the user's intent to section types based on descriptions and use_when hints.
3. If you need more detail about a section type, call get_section_detail.
4. Call list_app_sections to see what the user's app already supports.
5. Use compose_report to propose a configuration. The frontend will show a live preview.
6. Iterate with the user — add, remove, reorder sections based on their feedback.
7. Only call save_template when the user explicitly says to save.

RULES:
- Never ask the user to name section types. Map their natural language to types yourself.
- Be concise. Show what you're building, don't explain the system.
- When proposing sections, briefly explain WHY each maps to their request.
- If the user's request doesn't map to any section type, say so honestly.
"""

MAX_TOOL_ROUNDS = 5


def _summarize_tool_result(name: str, result_str: str) -> str:
    """Extract a short label from a tool result for the UI badge."""
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return "done"

    if name == "list_section_types":
        sections = data.get("sections", [])
        return f"{len(sections)} types"
    if name == "list_app_sections":
        app_id = data.get("app_id", "")
        sections = data.get("sections", [])
        return f"{app_id} · {len(sections)} sections" if app_id else f"{len(sections)} sections"
    if name == "get_section_detail":
        return data.get("key", data.get("label", "done"))
    if name == "compose_report":
        sections = data.get("sections", [])
        return f"{len(sections)} sections"
    if name == "save_template":
        return data.get("report_name", "saved")
    return "done"


async def run_chat_turn(
    session: dict[str, Any],
    user_message: str,
    *,
    provider: str,
    model: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Process one user message through the LLM with tool calling.
    Returns the final assistant response + any composed report config.
    """
    adapter = await create_adapter(
        provider=provider,
        model=model,
        tenant_id=session["tenant_id"],
        user_id=session["user_id"],
    )

    session["messages"].append(adapter.build_user_message(user_message))

    composed_report: dict | None = None
    tool_call_log: list[dict[str, str]] = []

    async def dispatch(name: str, arguments: dict) -> str:
        nonlocal composed_report

        result_str = await dispatch_tool_call(
            name, arguments,
            db=db,
            tenant_id=session["tenant_id"],
            user_id=session["user_id"],
            app_id=session["app_id"],
        )

        summary = _summarize_tool_result(name, result_str)
        tool_call_log.append({"name": name, "summary": summary})

        if name == "compose_report":
            parsed = json.loads(result_str)
            if parsed.get("status") == "ok":
                composed_report = parsed

        if name == "save_template":
            await db.commit()

        return result_str

    text, session["messages"] = await run_tool_loop(
        adapter=adapter,
        messages=session["messages"],
        tools=TOOLS,
        system=SYSTEM_PROMPT,
        temperature=0.3,
        dispatch_fn=dispatch,
        max_rounds=MAX_TOOL_ROUNDS,
    )

    if text is None:
        text = "I've reached the maximum number of tool calls for this turn. Please try a simpler request."

    return {
        "role": "assistant",
        "content": text,
        "tool_calls": tool_call_log,
        "composed_report": composed_report,
    }
```

- [ ] **Step 3: Update route to return tool_calls**

In `backend/app/routes/report_builder.py`, add `ToolCallOut` to imports:

```python
from app.services.report_builder.schemas import (
    BuilderChatRequest,
    BuilderChatResponse,
    ComposedReportOut,
    ToolCallOut,
)
```

Update the response construction (replace lines 57-61):

```python
    return BuilderChatResponse(
        session_id=session_id,
        content=result.get("content", ""),
        tool_calls=[
            ToolCallOut(name=tc["name"], summary=tc["summary"])
            for tc in result.get("tool_calls", [])
        ],
        composed_report=composed,
    )
```

- [ ] **Step 4: Verify imports**

```bash
source $(pyenv prefix venv-python-ai-evals-arize)/bin/activate
PYTHONPATH=backend python -c "from app.routes.report_builder import router; print('ok')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_builder/schemas.py backend/app/services/report_builder/chat_handler.py backend/app/routes/report_builder.py
git commit -m "feat: track tool call summaries in chat response"
```

---

### Task 2: Backend — /api/chat-engine/defaults endpoint

**Files:**
- Create: `backend/app/routes/chat_engine.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the defaults endpoint**

```python
# backend/app/routes/chat_engine.py
"""API routes for the chat engine."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from app.auth import AuthContext, get_auth_context

router = APIRouter(prefix="/api/chat-engine", tags=["chat-engine"])


@router.get("/defaults")
async def get_defaults(auth: AuthContext = Depends(get_auth_context)):
    """Return default model per provider for the chat widget."""
    return {
        "gemini": {
            "model": os.getenv("GEMINI_MODEL", "") or "gemini-2.5-flash",
        },
        "openai": {
            "model": os.getenv("OPENAI_MODEL", "") or "gpt-4o-mini",
        },
    }
```

- [ ] **Step 2: Register in main.py**

Add after line 262 in `backend/app/main.py`:

```python
from app.routes.chat_engine import router as chat_engine_router
```

Add after line 286:

```python
app.include_router(chat_engine_router)
```

- [ ] **Step 3: Verify**

```bash
PYTHONPATH=backend python -c "from app.routes.chat_engine import router; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/chat_engine.py backend/app/main.py
git commit -m "feat: add /api/chat-engine/defaults endpoint"
```

---

### Task 3: Frontend — types + api

**Files:**
- Create: `src/features/chat-widget/types.ts`
- Create: `src/features/chat-widget/api.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// src/features/chat-widget/types.ts
import type { ComposedReport } from '@/features/reportBuilder/types';

export type ChatProvider = 'gemini' | 'openai';

export interface ToolCallBadgeData {
  name: string;
  summary?: string;
  status: 'running' | 'done';
}

export interface WidgetMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls: ToolCallBadgeData[];
  composedReport?: ComposedReport | null;
  status: 'complete' | 'streaming' | 'error';
}

export interface ChatDefaults {
  gemini: { model: string };
  openai: { model: string };
}

export interface PromptTemplate {
  label: string;
  prompt: string;
  category?: string;
}

export interface ChatWidgetConfig {
  enabled?: boolean;
  promptTemplates?: PromptTemplate[];
  capabilities?: string[];
}
```

- [ ] **Step 2: Create api.ts**

```typescript
// src/features/chat-widget/api.ts
import { apiRequest } from '@/services/api/client';
import type { ChatDefaults, ToolCallBadgeData } from './types';
import type { ComposedReport } from '@/features/reportBuilder/types';

interface ChatRequest {
  appId: string;
  sessionId: string | null;
  message: string;
  provider: string;
  model: string;
}

interface ChatResponse {
  sessionId: string;
  role: string;
  content: string;
  toolCalls: Array<{ name: string; summary: string }>;
  composedReport: ComposedReport | null;
}

export async function sendChatMessage(body: ChatRequest): Promise<ChatResponse> {
  return apiRequest<ChatResponse>('/api/report-builder/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getChatDefaults(): Promise<ChatDefaults> {
  return apiRequest<ChatDefaults>('/api/chat-engine/defaults');
}

export async function streamChatMessage(
  body: ChatRequest,
  callbacks: {
    onToolCallStart: (name: string) => void;
    onToolCallEnd: (name: string, summary: string) => void;
    onContentDelta: (delta: string) => void;
    onDone: (data: { toolCalls: Array<{ name: string; summary: string }>; composedReport: ComposedReport | null }) => void;
    onError: (error: string) => void;
  },
): Promise<AbortController> {
  const controller = new AbortController();
  const token = localStorage.getItem('access_token') || '';

  fetch('/api/report-builder/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        callbacks.onError(`API error ${res.status}`);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) { callbacks.onError('No response body'); return; }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const raw = line.slice(6);
            try {
              const data = JSON.parse(raw);
              if (eventType === 'tool_call_start') callbacks.onToolCallStart(data.name);
              else if (eventType === 'tool_call_end') callbacks.onToolCallEnd(data.name, data.summary);
              else if (eventType === 'content_delta') callbacks.onContentDelta(data.delta);
              else if (eventType === 'done') callbacks.onDone(data);
              else if (eventType === 'error') callbacks.onError(data.message || 'Unknown error');
            } catch { /* skip malformed */ }
            eventType = '';
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') callbacks.onError(String(err));
    });

  return controller;
}
```

- [ ] **Step 3: Verify build**

```bash
npx tsc -b --noEmit 2>&1 | grep "chat-widget" | head -5
```

- [ ] **Step 4: Commit**

```bash
git add src/features/chat-widget/types.ts src/features/chat-widget/api.ts
git commit -m "feat(chat-widget): add types and API client"
```

---

### Task 4: Frontend — Zustand store

**Files:**
- Create: `src/features/chat-widget/useChatWidget.ts`

- [ ] **Step 1: Create the store**

```typescript
// src/features/chat-widget/useChatWidget.ts
import { create } from 'zustand';
import { sendChatMessage, getChatDefaults } from './api';
import type { ChatDefaults, ChatProvider, WidgetMessage } from './types';

let msgCounter = 0;
const nextId = () => `msg_${++msgCounter}`;

interface ChatWidgetStore {
  // UI
  open: boolean;
  toggle: () => void;
  openWithPrompt: (prompt: string) => void;

  // Session
  sessionId: string | null;
  provider: ChatProvider | null;
  locked: boolean;
  messages: WidgetMessage[];
  status: 'idle' | 'sending' | 'error';
  activeToolCall: string | null;

  // Actions
  setProvider: (p: ChatProvider) => void;
  send: (text: string, appId: string) => Promise<void>;
  reset: () => void;

  // Defaults
  defaults: ChatDefaults | null;
  loadDefaults: () => Promise<void>;
}

export const useChatWidgetStore = create<ChatWidgetStore>((set, get) => ({
  // UI
  open: false,
  toggle: () => set((s) => ({ open: !s.open })),
  openWithPrompt: (prompt) => {
    set({ open: true });
    // Defer send to next tick so the widget renders first
    const { provider } = get();
    if (provider) {
      // appId will be read from the caller context
      // This is a convenience — caller should use send() directly after opening
    }
  },

  // Session
  sessionId: null,
  provider: null,
  locked: false,
  messages: [],
  status: 'idle',
  activeToolCall: null,

  // Actions
  setProvider: (p) => {
    if (get().locked) return;
    set({ provider: p });
  },

  send: async (text, appId) => {
    const { provider, defaults, sessionId } = get();
    if (!provider || !defaults) return;

    const model = defaults[provider].model;

    // Add user message optimistically
    const userMsg: WidgetMessage = {
      id: nextId(),
      role: 'user',
      content: text,
      toolCalls: [],
      status: 'complete',
    };

    // Add placeholder assistant message
    const assistantId = nextId();
    const assistantMsg: WidgetMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      toolCalls: [],
      status: 'streaming',
    };

    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      status: 'sending',
      locked: true,
    }));

    try {
      const response = await sendChatMessage({
        appId,
        sessionId,
        message: text,
        provider,
        model,
      });

      set((s) => ({
        sessionId: response.sessionId,
        status: 'idle',
        messages: s.messages.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: response.content,
                toolCalls: response.toolCalls.map((tc) => ({
                  name: tc.name,
                  summary: tc.summary,
                  status: 'done' as const,
                })),
                composedReport: response.composedReport,
                status: 'complete' as const,
              }
            : m,
        ),
      }));
    } catch (err) {
      set((s) => ({
        status: 'error',
        messages: s.messages.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: err instanceof Error ? err.message : 'Request failed',
                status: 'error' as const,
              }
            : m,
        ),
      }));
    }
  },

  reset: () =>
    set({
      sessionId: null,
      locked: false,
      messages: [],
      status: 'idle',
      activeToolCall: null,
    }),

  // Defaults
  defaults: null,
  loadDefaults: async () => {
    try {
      const defaults = await getChatDefaults();
      set({ defaults });
    } catch {
      // Silently fail — widget will show error state
    }
  },
}));
```

- [ ] **Step 2: Verify build**

```bash
npx tsc -b --noEmit 2>&1 | grep "useChatWidget" | head -5
```

- [ ] **Step 3: Commit**

```bash
git add src/features/chat-widget/useChatWidget.ts
git commit -m "feat(chat-widget): add Zustand store with send/reset/defaults"
```

---

### Task 5: Frontend — ProviderToggle + PromptChips + ChatInput

**Files:**
- Create: `src/features/chat-widget/ProviderToggle.tsx`
- Create: `src/features/chat-widget/PromptChips.tsx`
- Create: `src/features/chat-widget/ChatInput.tsx`

- [ ] **Step 1: Create ProviderToggle.tsx**

```tsx
// src/features/chat-widget/ProviderToggle.tsx
import { cn } from '@/utils/cn';
import { Lock } from 'lucide-react';
import type { ChatProvider } from './types';

interface ProviderToggleProps {
  selected: ChatProvider | null;
  onSelect: (p: ChatProvider) => void;
  locked: boolean;
  disabled: Record<ChatProvider, boolean>;
}

const PROVIDERS: Array<{ value: ChatProvider; label: string; color: string }> = [
  { value: 'gemini', label: 'Gemini', color: 'var(--color-level-easy)' },
  { value: 'openai', label: 'OpenAI', color: '#10A37F' },
];

export function ProviderToggle({ selected, onSelect, locked, disabled }: ProviderToggleProps) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border-subtle)]">
      {PROVIDERS.map((p) => {
        if (locked && selected !== p.value) return null;
        const isActive = selected === p.value;
        const isDisabled = disabled[p.value];

        return (
          <button
            key={p.value}
            onClick={() => !locked && !isDisabled && onSelect(p.value)}
            disabled={isDisabled || locked}
            title={isDisabled ? 'Configure in Settings → LLM Auth' : undefined}
            className={cn(
              'inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-all',
              'border',
              isActive
                ? 'border-[var(--color-brand-primary)] bg-[var(--color-brand-accent)] text-[var(--color-brand-primary)]'
                : 'border-[var(--border-default)] text-[var(--text-muted)]',
              isDisabled && 'opacity-40 cursor-not-allowed',
              !isDisabled && !locked && !isActive && 'hover:border-[var(--border-strong)] cursor-pointer',
            )}
          >
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: p.color }}
            />
            {p.label}
            {locked && isActive && <Lock className="h-2.5 w-2.5" />}
          </button>
        );
      })}
      {locked && selected && (
        <span className="ml-auto text-[10px] font-mono text-[var(--text-muted)]">
          {selected === 'gemini' ? 'gemini-2.5-flash' : 'gpt-4o-mini'}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create PromptChips.tsx**

```tsx
// src/features/chat-widget/PromptChips.tsx
import type { PromptTemplate } from './types';

interface PromptChipsProps {
  templates: PromptTemplate[];
  onSelect: (prompt: string) => void;
}

export function PromptChips({ templates, onSelect }: PromptChipsProps) {
  if (templates.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 justify-center mt-3">
      {templates.map((t) => (
        <button
          key={t.label}
          onClick={() => onSelect(t.prompt)}
          className="text-[11px] px-3 py-1.5 rounded-full border border-[var(--border-default)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--color-brand-primary)] hover:text-[var(--color-brand-primary)] hover:bg-[var(--color-brand-accent)] transition-all truncate max-w-[200px]"
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create ChatInput.tsx**

```tsx
// src/features/chat-widget/ChatInput.tsx
import { useState, useCallback, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';
import { cn } from '@/utils/cn';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text || disabled) return;
    setValue('');
    onSend(text);
    // Reset textarea height
    if (ref.current) ref.current.style.height = 'auto';
  }, [value, disabled, onSend]);

  // Auto-resize textarea
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [value]);

  return (
    <div className="flex items-end gap-2 px-4 py-2.5 border-t border-[var(--border-default)]">
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder={placeholder ?? 'Type a message...'}
        disabled={disabled}
        rows={1}
        className={cn(
          'flex-1 resize-none rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)]',
          'px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)]',
          'focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]',
          'min-h-[36px] max-h-[120px]',
        )}
      />
      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors',
          'bg-[var(--color-brand-primary)] text-white',
          'hover:bg-[var(--color-brand-primary-hover)]',
          'disabled:opacity-40 disabled:cursor-not-allowed',
        )}
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
npx tsc -b --noEmit 2>&1 | grep "chat-widget" | head -10
```

- [ ] **Step 5: Commit**

```bash
git add src/features/chat-widget/ProviderToggle.tsx src/features/chat-widget/PromptChips.tsx src/features/chat-widget/ChatInput.tsx
git commit -m "feat(chat-widget): add ProviderToggle, PromptChips, ChatInput"
```

---

### Task 6: Frontend — ToolCallBadge + ChatMessages

**Files:**
- Create: `src/features/chat-widget/ToolCallBadge.tsx`
- Create: `src/features/chat-widget/ChatMessages.tsx`

- [ ] **Step 1: Ensure remark-gfm is installed**

```bash
npm ls remark-gfm 2>/dev/null || npm install remark-gfm
```

- [ ] **Step 2: Create ToolCallBadge.tsx**

```tsx
// src/features/chat-widget/ToolCallBadge.tsx
import { cn } from '@/utils/cn';
import { Wrench, Check } from 'lucide-react';
import type { ToolCallBadgeData } from './types';

export function ToolCallBadge({ name, summary, status }: ToolCallBadgeData) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono font-medium',
        'bg-[var(--color-brand-accent)] text-[var(--color-brand-primary)]',
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
    </span>
  );
}
```

- [ ] **Step 3: Create ChatMessages.tsx**

```tsx
// src/features/chat-widget/ChatMessages.tsx
import { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Loader2, Sparkles } from 'lucide-react';
import { cn } from '@/utils/cn';
import { ToolCallBadge } from './ToolCallBadge';
import { PromptChips } from './PromptChips';
import type { WidgetMessage, PromptTemplate } from './types';

interface ChatMessagesProps {
  messages: WidgetMessage[];
  status: 'idle' | 'sending' | 'error';
  promptTemplates: PromptTemplate[];
  onPromptSelect: (prompt: string) => void;
}

export function ChatMessages({ messages, status, promptTemplates, onPromptSelect }: ChatMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, status]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-2.5">
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-center px-4">
          <Sparkles className="h-8 w-8 text-[var(--text-muted)] mb-3" />
          <p className="text-sm text-[var(--text-muted)] max-w-[280px] leading-relaxed">
            Ask me to build reports, explore data, or analyze evaluation results.
          </p>
          <PromptChips templates={promptTemplates} onSelect={onPromptSelect} />
        </div>
      )}

      {messages.map((msg) => (
        <div
          key={msg.id}
          className={cn(
            'flex gap-2 max-w-[92%]',
            msg.role === 'user' ? 'ml-auto flex-row-reverse' : 'mr-auto',
          )}
        >
          {/* Avatar */}
          <div
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white',
              msg.role === 'user' ? 'bg-[var(--color-brand-primary)]' : 'bg-[var(--color-level-easy)]',
            )}
          >
            {msg.role === 'user' ? 'Y' : 'AI'}
          </div>

          {/* Bubble */}
          <div
            className={cn(
              'rounded-lg px-3 py-2 text-[13px] leading-relaxed',
              msg.role === 'user'
                ? 'bg-[var(--color-brand-primary)] text-white rounded-br-sm'
                : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded-bl-sm',
              msg.status === 'error' && 'border border-[var(--color-verdict-fail)] bg-[var(--color-verdict-fail)]/5',
            )}
          >
            {/* Tool call badges */}
            {msg.toolCalls.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {msg.toolCalls.map((tc) => (
                  <ToolCallBadge key={tc.name} {...tc} />
                ))}
              </div>
            )}

            {/* Content */}
            {msg.role === 'assistant' && msg.content ? (
              <div className="prose prose-sm max-w-none [&_p]:mb-1.5 [&_p:last-child]:mb-0 [&_ul]:mb-1.5 [&_li]:mb-0 [&_table]:text-xs [&_th]:px-2 [&_th]:py-1 [&_td]:px-2 [&_td]:py-1 [&_table]:border-collapse [&_th]:border [&_th]:border-[var(--border-subtle)] [&_td]:border [&_td]:border-[var(--border-subtle)] [&_th]:bg-[var(--bg-secondary)] [&_strong]:text-[var(--text-primary)] [&_code]:text-[11px] [&_code]:bg-[var(--bg-secondary)] [&_code]:px-1 [&_code]:rounded">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            ) : (
              <span>{msg.content}</span>
            )}

            {/* Streaming placeholder */}
            {msg.status === 'streaming' && !msg.content && msg.toolCalls.length === 0 && (
              <span className="flex items-center gap-1.5 text-[var(--text-muted)]">
                <Loader2 className="h-3 w-3 animate-spin" /> Thinking&hellip;
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

```bash
npx tsc -b --noEmit 2>&1 | grep "chat-widget" | head -10
```

- [ ] **Step 5: Commit**

```bash
git add src/features/chat-widget/ToolCallBadge.tsx src/features/chat-widget/ChatMessages.tsx
git commit -m "feat(chat-widget): add ToolCallBadge and ChatMessages with ReactMarkdown"
```

---

### Task 7: Frontend — ChatWidget container

**Files:**
- Create: `src/features/chat-widget/ChatWidget.tsx`

- [ ] **Step 1: Create ChatWidget.tsx**

```tsx
// src/features/chat-widget/ChatWidget.tsx
import { useEffect, useCallback } from 'react';
import { MessageCircle, X, Minus, Plus } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useAppStore } from '@/stores';
import { useLLMSettingsStore, hasProviderCredentials } from '@/stores/llmSettingsStore';
import { useChatWidgetStore } from './useChatWidget';
import { ProviderToggle } from './ProviderToggle';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import type { ChatProvider, ChatWidgetConfig } from './types';

export function ChatWidget() {
  const currentApp = useAppStore((s) => s.currentApp);
  const appConfig = useAppStore((s) => s.getAppConfig(currentApp));
  const chatConfig: ChatWidgetConfig = (appConfig as any)?.chat ?? {};

  const open = useChatWidgetStore((s) => s.open);
  const toggle = useChatWidgetStore((s) => s.toggle);
  const provider = useChatWidgetStore((s) => s.provider);
  const locked = useChatWidgetStore((s) => s.locked);
  const messages = useChatWidgetStore((s) => s.messages);
  const status = useChatWidgetStore((s) => s.status);
  const defaults = useChatWidgetStore((s) => s.defaults);
  const setProvider = useChatWidgetStore((s) => s.setProvider);
  const send = useChatWidgetStore((s) => s.send);
  const reset = useChatWidgetStore((s) => s.reset);
  const loadDefaults = useChatWidgetStore((s) => s.loadDefaults);

  // Load defaults on mount
  useEffect(() => {
    if (!defaults) void loadDefaults();
  }, [defaults, loadDefaults]);

  // Credential check
  const geminiApiKey = useLLMSettingsStore((s) => s.geminiApiKey);
  const openaiApiKey = useLLMSettingsStore((s) => s.openaiApiKey);
  const azureApiKey = useLLMSettingsStore((s) => s.azureOpenaiApiKey);
  const azureEndpoint = useLLMSettingsStore((s) => s.azureOpenaiEndpoint);
  const saConfigured = useLLMSettingsStore((s) => s._serviceAccountConfigured);

  const credState = { geminiApiKey, openaiApiKey, azureOpenaiApiKey: azureApiKey, azureOpenaiEndpoint: azureEndpoint, anthropicApiKey: '', _serviceAccountConfigured: saConfigured };
  const providerDisabled: Record<ChatProvider, boolean> = {
    gemini: !hasProviderCredentials('gemini', credState),
    openai: !hasProviderCredentials('openai', credState) && !hasProviderCredentials('azure_openai', credState),
  };

  const handleSend = useCallback(
    (text: string) => void send(text, currentApp),
    [send, currentApp],
  );

  const promptTemplates = chatConfig.promptTemplates ?? [];

  // Don't render if chat not enabled (default: enabled if key missing)
  if (chatConfig.enabled === false) return null;

  // Collapsed bubble
  if (!open) {
    return (
      <button
        onClick={toggle}
        className={cn(
          'fixed bottom-6 right-6 z-[var(--z-overlay)]',
          'flex h-14 w-14 items-center justify-center rounded-full',
          'bg-[var(--color-brand-primary)] text-white shadow-lg',
          'hover:bg-[var(--color-brand-primary-hover)] hover:scale-105',
          'transition-all duration-150',
        )}
        aria-label="Open AI Assistant"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    );
  }

  // Expanded widget
  const canSend = !!provider && !providerDisabled[provider] && status !== 'sending' && !!defaults;

  return (
    <div
      className={cn(
        'fixed bottom-6 right-6 z-[var(--z-overlay)]',
        'flex flex-col overflow-hidden rounded-2xl bg-[var(--bg-primary)] shadow-2xl',
        'border border-[var(--border-default)]',
        'w-[420px] h-[560px] min-w-[360px] min-h-[400px] max-w-[600px] max-h-[80vh]',
      )}
      style={{ resize: 'both', overflow: 'hidden', direction: 'rtl' }}
    >
      <div style={{ direction: 'ltr' }} className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-[var(--color-brand-accent)]">
              <MessageCircle className="h-3.5 w-3.5 text-[var(--color-brand-primary)]" />
            </div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">AI Assistant</h3>
            <span className="text-[10px] font-medium text-[var(--color-brand-primary)] bg-[var(--color-brand-accent)] px-1.5 py-0.5 rounded">
              {currentApp}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={reset}
              title="New chat"
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={toggle}
              title="Minimize"
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => { toggle(); reset(); }}
              title="Close"
              className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Provider toggle */}
        <ProviderToggle
          selected={provider}
          onSelect={setProvider}
          locked={locked}
          disabled={providerDisabled}
        />

        {/* Messages */}
        <ChatMessages
          messages={messages}
          status={status}
          promptTemplates={promptTemplates}
          onPromptSelect={handleSend}
        />

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          disabled={!canSend}
          placeholder={
            !provider
              ? 'Select a provider to start...'
              : !defaults
                ? 'Loading...'
                : `Ask about ${currentApp}...`
          }
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
npx tsc -b --noEmit 2>&1 | grep "chat-widget" | head -10
```

- [ ] **Step 3: Commit**

```bash
git add src/features/chat-widget/ChatWidget.tsx
git commit -m "feat(chat-widget): add floating ChatWidget container with bubble/panel"
```

---

### Task 8: Integration — MainLayout + ReportTab + delete BuilderOverlay

**Files:**
- Modify: `src/components/layout/MainLayout.tsx`
- Modify: `src/features/evalRuns/components/report/ReportTab.tsx`
- Delete: `src/features/reportBuilder/components/BuilderOverlay.tsx`

- [ ] **Step 1: Add ChatWidget to MainLayout**

In `src/components/layout/MainLayout.tsx`, add import after line 14:

```typescript
import { ChatWidget } from '@/features/chat-widget/ChatWidget';
```

Add `<ChatWidget />` after line 84 (before `<OfflineBanner />`):

```tsx
      <ChatWidget />
      <OfflineBanner />
```

- [ ] **Step 2: Update ReportTab to use widget instead of overlay**

In `src/features/evalRuns/components/report/ReportTab.tsx`:

Remove the `BuilderOverlay` import (line 12):
```typescript
// DELETE: import { BuilderOverlay } from '@/features/reportBuilder/components/BuilderOverlay';
```

Add the widget store import:
```typescript
import { useChatWidgetStore } from '@/features/chat-widget/useChatWidget';
```

Remove the `showBuilder` state (line 169):
```typescript
// DELETE: const [showBuilder, setShowBuilder] = useState(false);
```

Replace the button onClick (lines 571-581):
```tsx
      <Tooltip content="Build custom report">
        <Button
          size="sm"
          variant="secondary"
          iconOnly
          icon={Wand2}
          onClick={() => {
            const store = useChatWidgetStore.getState();
            store.toggle();
          }}
          title="Build Your Own Report"
          aria-label="Build Your Own Report"
        />
      </Tooltip>
```

Remove the `BuilderOverlay` component render (lines 671-676):
```tsx
// DELETE the entire <BuilderOverlay ... /> block
```

- [ ] **Step 3: Delete BuilderOverlay**

```bash
rm src/features/reportBuilder/components/BuilderOverlay.tsx
```

- [ ] **Step 4: Verify build**

```bash
npx tsc -b --noEmit 2>&1 | head -20
```

- [ ] **Step 5: Commit**

```bash
git add src/components/layout/MainLayout.tsx src/features/evalRuns/components/report/ReportTab.tsx
git rm src/features/reportBuilder/components/BuilderOverlay.tsx
git commit -m "feat: integrate ChatWidget into MainLayout, remove BuilderOverlay"
```

---

### Task 9: Backend — SSE streaming endpoint

**Files:**
- Modify: `backend/app/routes/report_builder.py`
- Modify: `backend/app/services/report_builder/chat_handler.py`

- [ ] **Step 1: Add streaming run_chat_turn variant to chat_handler**

Add at the bottom of `backend/app/services/report_builder/chat_handler.py`:

```python
import asyncio


async def run_chat_turn_streaming(
    session: dict[str, Any],
    user_message: str,
    *,
    provider: str,
    model: str,
    db: AsyncSession,
):
    """
    Generator version of run_chat_turn that yields SSE events.
    Yields dicts: {"event": str, "data": dict}
    """
    adapter = await create_adapter(
        provider=provider,
        model=model,
        tenant_id=session["tenant_id"],
        user_id=session["user_id"],
    )

    session["messages"].append(adapter.build_user_message(user_message))

    composed_report: dict | None = None
    tool_call_log: list[dict[str, str]] = []

    async def dispatch(name: str, arguments: dict) -> str:
        nonlocal composed_report

        yield_queue.append({"event": "tool_call_start", "data": {"name": name}})

        result_str = await dispatch_tool_call(
            name, arguments,
            db=db,
            tenant_id=session["tenant_id"],
            user_id=session["user_id"],
            app_id=session["app_id"],
        )

        summary = _summarize_tool_result(name, result_str)
        tool_call_log.append({"name": name, "summary": summary})
        yield_queue.append({"event": "tool_call_end", "data": {"name": name, "summary": summary}})

        if name == "compose_report":
            parsed = json.loads(result_str)
            if parsed.get("status") == "ok":
                composed_report = parsed

        if name == "save_template":
            await db.commit()

        return result_str

    # We use a queue pattern since dispatch is called inside run_tool_loop
    # and we can't yield from a nested async function
    yield_queue: list[dict] = []

    text, session["messages"] = await run_tool_loop(
        adapter=adapter,
        messages=session["messages"],
        tools=TOOLS,
        system=SYSTEM_PROMPT,
        temperature=0.3,
        dispatch_fn=dispatch,
        max_rounds=MAX_TOOL_ROUNDS,
    )

    if text is None:
        text = "I've reached the maximum number of tool calls for this turn. Please try a simpler request."

    # Yield all queued tool call events
    for event in yield_queue:
        yield event

    # Yield final content as a single delta (non-chunked for now)
    yield {"event": "content_delta", "data": {"delta": text}}

    # Yield done
    composed_out = None
    if composed_report:
        composed_out = {
            "reportName": composed_report.get("report_name"),
            "sections": composed_report.get("sections", []),
        }

    yield {
        "event": "done",
        "data": {
            "toolCalls": tool_call_log,
            "composedReport": composed_out,
        },
    }
```

- [ ] **Step 2: Add streaming endpoint to routes**

Add to `backend/app/routes/report_builder.py`:

```python
import json
from fastapi.responses import StreamingResponse
from app.services.report_builder.chat_handler import run_chat_turn_streaming
```

Add after the existing `/chat` endpoint:

```python
@router.post("/chat/stream")
async def chat_stream(
    body: BuilderChatRequest,
    auth: AuthContext = Depends(get_auth_context),
    db=Depends(get_db),
):
    if body.session_id:
        session = get_session(body.session_id)
    else:
        session = None

    if not session:
        session_id, session = create_session(
            app_id=body.app_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            provider=body.provider,
            model=body.model,
        )
    else:
        session_id = body.session_id

    async def event_generator():
        yield f"data: {json.dumps({'sessionId': session_id})}\n\n"
        async for event in run_chat_turn_streaming(
            session, body.message,
            provider=body.provider, model=body.model, db=db,
        ):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 3: Verify imports**

```bash
source $(pyenv prefix venv-python-ai-evals-arize)/bin/activate
PYTHONPATH=backend python -c "from app.routes.report_builder import router; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/report_builder/chat_handler.py backend/app/routes/report_builder.py
git commit -m "feat: add SSE streaming endpoint for chat"
```

---

### Task 10: Verify full stack

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

```bash
source $(pyenv prefix venv-python-ai-evals-arize)/bin/activate
PYTHONPATH=backend python -m pytest backend/tests/test_chat_engine_unittest.py -v
```

- [ ] **Step 2: Run frontend build**

```bash
npx tsc -b --noEmit
```

- [ ] **Step 3: Verify all imports**

```bash
PYTHONPATH=backend python -c "
from app.routes.report_builder import router
from app.routes.chat_engine import router as ce_router
from app.services.report_builder.chat_handler import run_chat_turn, run_chat_turn_streaming
print('all backend imports ok')
"
```

- [ ] **Step 4: Check commit history**

```bash
git log --oneline -12
```
