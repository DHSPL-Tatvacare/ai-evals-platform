# Phase 2: Inside Sales — LSQ Client + Listing Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend LSQ API client and the frontend call listing page — the primary data browsing interface for Inside Sales.

**Architecture:** Backend creates an `LSQClient` service that proxies LeadSquared API calls with pagination, rate limiting, and lead name caching. A new `/api/inside-sales/calls` route exposes this to the frontend. Frontend builds a table-based listing page with server-side pagination, a right-slide filter panel, bulk selection, and call detail drilldown.

**Tech Stack:** Python (FastAPI, httpx), TypeScript (React, Zustand), existing `AudioPlayer` (wavesurfer.js), existing UI components (`Tabs`, `Button`, `EmptyState`).

**Branch:** `feat/phase-2-lsq-listing`

**Depends on:** Phase 1 (app shell must be in place).

---

## Background

LeadSquared API provides call activity data via `POST /v2/ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent`. Each activity has agent name, phone, duration, recording URL, status, and a `RelatedProspectId` that requires a second API call to resolve the lead name.

The listing page paginates directly against LSQ — no local sync. Backend handles the 2-call-per-page pattern (activities + lead hydration).

**LSQ API details** are documented in `docs/plans/call-quality-evals/overview.md` — reference that file for field mappings, event codes, and rate limits.

## Key files to reference

- `docs/plans/call-quality-evals/overview.md` — LSQ API docs, field mappings, event codes
- `docs/plans/call-quality-evals/inside-sales-design.md` — design spec section 4 (Listing Page)
- `backend/app/routes/listings.py` — reference for route patterns (auth, pagination, app_id filtering)
- `backend/app/schemas/base.py` — `CamelModel` / `CamelORMModel` base classes
- `backend/app/auth/context.py` — `AuthContext`, `get_auth_context`
- `src/features/voiceRx/pages/VoiceRxRunList.tsx` — reference for sticky header, search, filter chips
- `src/features/transcript/components/AudioPlayer.tsx` — reuse for playback
- `src/components/ui/EmptyState.tsx` — zero states
- `src/services/api/client.ts` — `apiRequest` for all HTTP calls

## Guidelines

- **Backend:** All new routes require `auth: AuthContext = Depends(get_auth_context)`. Use `CamelModel` for request schemas, `CamelORMModel` for responses.
- **Frontend:** Use `apiRequest` for all HTTP. Use `cn()` for class merging. Use CSS variables for all colors. Use `routes.ts` constants for all paths.
- **LSQ credentials:** Store in environment variables (`LSQ_ACCESS_KEY`, `LSQ_SECRET_KEY`, `LSQ_BASE_URL`). Never hardcode.
- **Rate limiting:** LSQ allows 25 API calls per 5 seconds. Implement a simple semaphore/delay in `LSQClient`.

---

### Task 1: Create LSQ API client (backend service)

**Files:**
- Create: `backend/app/services/lsq_client.py`

- [ ] **Step 1:** Read `docs/plans/call-quality-evals/overview.md` sections on API endpoints, field mappings, and rate limits.

- [ ] **Step 2:** Create the LSQ client service. This is a Python class that wraps httpx for LSQ API calls:

```python
"""LeadSquared API client for Inside Sales call data."""

import asyncio
import os
import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# In-memory lead name cache (process-lifetime)
_lead_cache: dict[str, str] = {}

LSQ_BASE_URL = os.getenv("LSQ_BASE_URL", "https://api-in21.leadsquared.com/v2")
LSQ_ACCESS_KEY = os.getenv("LSQ_ACCESS_KEY", "")
LSQ_SECRET_KEY = os.getenv("LSQ_SECRET_KEY", "")

# Rate limit: 25 requests per 5 seconds → ~200ms between calls
_rate_semaphore = asyncio.Semaphore(5)


def _auth_params() -> dict[str, str]:
    return {"accessKey": LSQ_ACCESS_KEY, "secretKey": LSQ_SECRET_KEY}


async def _rate_limited_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with rate limiting."""
    async with _rate_semaphore:
        resp = await client.request(method, url, **kwargs)
        resp.raise_for_status()
        await asyncio.sleep(0.2)  # 200ms spacing
        return resp


async def fetch_call_activities(
    date_from: str,
    date_to: str,
    event_codes: list[int] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Fetch phone call activities from LSQ.

    Returns: { "activities": [...], "total": int }
    """
    if event_codes is None:
        event_codes = [21, 22]  # Inbound + Outbound system telephony

    all_activities: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for event_code in event_codes:
            url = f"{LSQ_BASE_URL}/ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent"
            body = {
                "Parameter": {
                    "FromDate": date_from,
                    "ToDate": date_to,
                    "ActivityEvent": event_code,
                },
                "Paging": {
                    "PageIndex": page,
                    "PageSize": page_size,
                },
                "Sorting": {
                    "ColumnName": "CreatedOn",
                    "Direction": 1,  # Descending
                },
            }
            resp = await _rate_limited_request(
                client, "POST", url, params=_auth_params(), json=body
            )
            data = resp.json()
            if isinstance(data, list):
                all_activities.extend(data)

    return {"activities": all_activities, "total": len(all_activities)}


def _parse_source_data(note: str) -> dict[str, Any]:
    """Parse ActivityEvent_Note to extract SourceData JSON."""
    import json
    try:
        # Find SourceData JSON within the delimited string
        if "SourceData" in note:
            start = note.index('{"')
            # Find matching closing brace
            brace_count = 0
            for i, c in enumerate(note[start:], start):
                if c == '{': brace_count += 1
                elif c == '}': brace_count -= 1
                if brace_count == 0:
                    return json.loads(note[start:i+1])
        return {}
    except (ValueError, json.JSONDecodeError):
        return {}


def normalize_activity(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw LSQ activity into a clean call record."""
    source_data = _parse_source_data(raw.get("ActivityEvent_Note", ""))
    event_code = int(raw.get("ActivityEvent", 0))

    return {
        "activityId": raw.get("ProspectActivityId", ""),
        "prospectId": raw.get("RelatedProspectId", ""),
        "agentName": raw.get("CreatedByName", ""),
        "agentEmail": raw.get("CreatedByEmailAddress", ""),
        "eventCode": event_code,
        "direction": "inbound" if event_code == 21 else "outbound",
        "status": raw.get("Status", ""),
        "callStartTime": raw.get("mx_Custom_2", ""),
        "durationSeconds": int(raw.get("mx_Custom_3", 0) or 0),
        "recordingUrl": raw.get("mx_Custom_4", ""),
        "phoneNumber": source_data.get("DestinationNumber", ""),
        "displayNumber": raw.get("mx_Custom_1", ""),
        "callNotes": source_data.get("CallNotes", ""),
        "callSessionId": source_data.get("CallSessionId", ""),
        "createdOn": raw.get("CreatedOn", ""),
        "leadName": "",  # Hydrated separately
    }


async def hydrate_lead_names(
    prospect_ids: list[str],
) -> dict[str, str]:
    """Bulk fetch lead names for prospect IDs. Uses cache."""
    uncached = [pid for pid in prospect_ids if pid and pid not in _lead_cache]

    if uncached:
        async with httpx.AsyncClient(timeout=30) as client:
            # Batch in groups of 50
            for i in range(0, len(uncached), 50):
                batch = uncached[i:i+50]
                url = f"{LSQ_BASE_URL}/Leads.svc/Leads.GetByIds"
                params = {**_auth_params(), "ids": ",".join(batch)}
                try:
                    resp = await _rate_limited_request(
                        client, "GET", url, params=params
                    )
                    leads = resp.json()
                    if isinstance(leads, list):
                        for lead in leads:
                            pid = lead.get("ProspectID", "")
                            name = lead.get("FirstName", "")
                            last = lead.get("LastName", "")
                            full = f"{name} {last}".strip() or pid[:8]
                            _lead_cache[pid] = full
                except Exception as e:
                    logger.warning(f"Lead hydration failed for batch: {e}")
                    for pid in batch:
                        _lead_cache[pid] = pid[:8]  # Fallback to truncated ID

    return {pid: _lead_cache.get(pid, pid[:8]) for pid in prospect_ids}
```

- [ ] **Step 3:** Commit:
```bash
git add backend/app/services/lsq_client.py
git commit -m "feat: add LSQ API client with rate limiting and lead cache"
```

---

### Task 2: Create backend route and schemas

**Files:**
- Create: `backend/app/routes/inside_sales.py`
- Create: `backend/app/schemas/inside_sales.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1:** Create schemas in `backend/app/schemas/inside_sales.py`:

```python
"""Schemas for Inside Sales API."""

from datetime import datetime
from typing import Optional
from pydantic import Field
from app.schemas.base import CamelModel


class CallRecord(CamelModel):
    activity_id: str
    prospect_id: str
    agent_name: str
    agent_email: str
    event_code: int
    direction: str
    status: str
    call_start_time: str
    duration_seconds: int
    recording_url: str
    phone_number: str
    display_number: str
    call_notes: str
    call_session_id: str
    created_on: str
    lead_name: str


class CallListResponse(CamelModel):
    calls: list[CallRecord]
    total: int
    page: int
    page_size: int


class CallListParams(CamelModel):
    date_from: str = Field(..., description="Start date YYYY-MM-DD HH:MM:SS")
    date_to: str = Field(..., description="End date YYYY-MM-DD HH:MM:SS")
    page: int = 1
    page_size: int = 50
    agent: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    event_codes: Optional[str] = None  # Comma-separated
```

- [ ] **Step 2:** Create route in `backend/app/routes/inside_sales.py`:

```python
"""Routes for Inside Sales call data."""

from fastapi import APIRouter, Depends, Query
from app.auth.context import AuthContext, get_auth_context
from app.schemas.inside_sales import CallRecord, CallListResponse
from app.services.lsq_client import (
    fetch_call_activities,
    normalize_activity,
    hydrate_lead_names,
)

router = APIRouter(prefix="/api/inside-sales", tags=["inside-sales"])


@router.get("/calls", response_model=CallListResponse)
async def list_calls(
    date_from: str = Query(..., description="Start date YYYY-MM-DD HH:MM:SS"),
    date_to: str = Query(..., description="End date YYYY-MM-DD HH:MM:SS"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    agent: str | None = Query(None),
    direction: str | None = Query(None),
    status: str | None = Query(None),
    event_codes: str | None = Query(None, description="Comma-separated event codes"),
    auth: AuthContext = Depends(get_auth_context),
):
    """Fetch call activities from LSQ with lead name hydration."""
    # Parse event codes
    codes = None
    if event_codes:
        codes = [int(c.strip()) for c in event_codes.split(",")]

    # Fetch from LSQ
    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        event_codes=codes,
        page=page,
        page_size=page_size,
    )

    # Normalize activities
    calls = [normalize_activity(a) for a in result["activities"]]

    # Apply filters (LSQ API doesn't support all our filter needs)
    if agent:
        calls = [c for c in calls if agent.lower() in c["agentName"].lower()]
    if direction:
        calls = [c for c in calls if c["direction"] == direction]
    if status:
        calls = [c for c in calls if c["status"].lower() == status.lower()]

    # Hydrate lead names
    prospect_ids = [c["prospectId"] for c in calls if c["prospectId"]]
    name_map = await hydrate_lead_names(prospect_ids)
    for call in calls:
        call["leadName"] = name_map.get(call["prospectId"], "")

    return CallListResponse(
        calls=[CallRecord(**c) for c in calls],
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get("/calls/{activity_id}")
async def get_call(
    activity_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Get a single call detail by activity ID."""
    # For single call, we fetch from LSQ and hydrate
    # This will be implemented when call detail page needs it
    # For now, the listing data is sufficient
    return {"detail": "not yet implemented"}
```

- [ ] **Step 3:** Register the route in `backend/app/main.py`:

```python
from app.routes.inside_sales import router as inside_sales_router
# ...
app.include_router(inside_sales_router)
```

- [ ] **Step 4:** Add LSQ environment variables to `.env.example` or document in `docs/SETUP.md`:

```
LSQ_BASE_URL=https://api-in21.leadsquared.com/v2
LSQ_ACCESS_KEY=u$r6ec1c6a13b7d4d8d9448d9042a153d9d
LSQ_SECRET_KEY=4617b1110e6058e1f9311f79fb9005b23842aa81
```

- [ ] **Step 5:** Run backend to verify route registration:
```bash
PYTHONPATH=backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8721
# Check: GET http://localhost:8721/docs — /api/inside-sales/calls should appear
```

- [ ] **Step 6:** Commit:
```bash
git add backend/app/routes/inside_sales.py backend/app/schemas/inside_sales.py backend/app/main.py
git commit -m "feat: add inside-sales calls API route with LSQ proxy"
```

---

### Task 3: Create Zustand store for Inside Sales

**Files:**
- Create: `src/stores/insideSalesStore.ts`
- Modify: `src/stores/index.ts`

- [ ] **Step 1:** Read `src/stores/listingsStore.ts` for the store pattern.

- [ ] **Step 2:** Create the store. This manages call listing state, filters, pagination, and selected calls:

```typescript
import { create } from 'zustand';
import { apiRequest } from '@/services/api/client';

export interface CallRecord {
  activityId: string;
  prospectId: string;
  agentName: string;
  agentEmail: string;
  eventCode: number;
  direction: 'inbound' | 'outbound';
  status: string;
  callStartTime: string;
  durationSeconds: number;
  recordingUrl: string;
  phoneNumber: string;
  displayNumber: string;
  callNotes: string;
  callSessionId: string;
  createdOn: string;
  leadName: string;
}

export interface CallFilters {
  dateFrom: string;
  dateTo: string;
  agent: string;
  direction: string;
  status: string;
  eventCodes: string;
  evalStatus: string;
  durationMin: string;
  durationMax: string;
  scoreMin: string;
  scoreMax: string;
  search: string;
}

interface InsideSalesState {
  calls: CallRecord[];
  total: number;
  page: int;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
  filters: CallFilters;
  selectedCallIds: Set<string>;

  setFilters: (filters: Partial<CallFilters>) => void;
  clearFilters: () => void;
  setPage: (page: number) => void;
  toggleCallSelection: (activityId: string) => void;
  selectAllOnPage: () => void;
  deselectAll: () => void;
  loadCalls: () => Promise<void>;
  reset: () => void;
}

const DEFAULT_FILTERS: CallFilters = {
  dateFrom: new Date().toISOString().split('T')[0] + ' 00:00:00',
  dateTo: new Date().toISOString().split('T')[0] + ' 23:59:59',
  agent: '',
  direction: '',
  status: '',
  eventCodes: '',
  evalStatus: '',
  durationMin: '',
  durationMax: '',
  scoreMin: '',
  scoreMax: '',
  search: '',
};

export const useInsideSalesStore = create<InsideSalesState>((set, get) => ({
  calls: [],
  total: 0,
  page: 1,
  pageSize: 50,
  isLoading: false,
  error: null,
  filters: { ...DEFAULT_FILTERS },
  selectedCallIds: new Set(),

  setFilters: (updates) =>
    set((s) => ({ filters: { ...s.filters, ...updates }, page: 1 })),

  clearFilters: () => set({ filters: { ...DEFAULT_FILTERS }, page: 1 }),

  setPage: (page) => set({ page }),

  toggleCallSelection: (activityId) =>
    set((s) => {
      const next = new Set(s.selectedCallIds);
      if (next.has(activityId)) next.delete(activityId);
      else next.add(activityId);
      return { selectedCallIds: next };
    }),

  selectAllOnPage: () =>
    set((s) => ({
      selectedCallIds: new Set(s.calls.map((c) => c.activityId)),
    })),

  deselectAll: () => set({ selectedCallIds: new Set() }),

  loadCalls: async () => {
    const { filters, page, pageSize } = get();
    set({ isLoading: true, error: null });
    try {
      const params = new URLSearchParams({
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
        page: String(page),
        pageSize: String(pageSize),
      });
      if (filters.agent) params.set('agent', filters.agent);
      if (filters.direction) params.set('direction', filters.direction);
      if (filters.status) params.set('status', filters.status);
      if (filters.eventCodes) params.set('eventCodes', filters.eventCodes);

      const data = await apiRequest<{
        calls: CallRecord[];
        total: number;
        page: number;
        pageSize: number;
      }>(`/api/inside-sales/calls?${params.toString()}`);

      set({ calls: data.calls, total: data.total, isLoading: false });
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Failed to load calls',
        isLoading: false,
      });
    }
  },

  reset: () =>
    set({
      calls: [],
      total: 0,
      page: 1,
      isLoading: false,
      error: null,
      filters: { ...DEFAULT_FILTERS },
      selectedCallIds: new Set(),
    }),
}));
```

- [ ] **Step 3:** Export from `src/stores/index.ts`:
```typescript
export { useInsideSalesStore } from './insideSalesStore';
```

- [ ] **Step 4:** Run `npx tsc -b`.

- [ ] **Step 5:** Commit:
```bash
git add src/stores/insideSalesStore.ts src/stores/index.ts
git commit -m "feat: add insideSalesStore for call listing state"
```

---

### Task 4: Build the CallListingPage

**Files:**
- Replace: `src/features/insideSales/pages/InsideSalesListing.tsx`

- [ ] **Step 1:** Read the design spec section 4 (Listing Page) for the exact layout hierarchy.

- [ ] **Step 2:** Read `src/features/voiceRx/pages/VoiceRxRunList.tsx` for the sticky header, search input, and filter chip patterns. Match the exact CSS classes.

- [ ] **Step 3:** Build the listing page. Key structure:
  - Page header: h1 "Calls" + "Evaluate Selected" button (disabled until selection) + overflow menu
  - Tab bar (single tab "All Calls")
  - Search input (match VoiceRxRunList pattern: `w-full pl-8 pr-3 py-1.5 text-xs`)
  - Filter button + active pills + clear link + result count
  - Table with columns from design spec
  - Bulk action bar (contextual)
  - Pagination

The component should:
  - Call `loadCalls()` on mount and when filters/page change
  - Use `useInsideSalesStore` with slice selectors (never destructure full store)
  - Use `EmptyState` for zero states (no calls, search no match, API error)
  - Use `VerdictBadge` pattern for status badges
  - Use CSS variables for all colors

- [ ] **Step 4:** This is a large component. Build iteratively:
  1. First: page header + empty table structure + `loadCalls()` on mount
  2. Then: table rendering with data
  3. Then: pagination
  4. Then: search + filter pills
  5. Then: bulk selection (checkboxes + action bar)
  6. Then: zero states

Commit after each working increment.

- [ ] **Step 5:** Run `npm run dev` and verify:
  - Page loads with today's calls from LSQ
  - Pagination works
  - Search filters client-side
  - Filter pills show/dismiss correctly
  - Checkbox selection works
  - Empty states appear appropriately

---

### Task 5: Build the CallFilterPanel

**Files:**
- Create: `src/features/insideSales/components/CallFilterPanel.tsx`

- [ ] **Step 1:** This is a right-slide overlay. Follow the same pattern as the WizardOverlay backdrop + panel, but simpler (no steps). Reference the design spec filter panel section.

- [ ] **Step 2:** Build with:
  - Backdrop: `fixed inset-0 z-50 bg-overlay backdrop-blur-sm`
  - Panel: `fixed top-0 right-0 bottom-0 w-[380px] bg-primary` with slide animation
  - Form groups: Date range, Agent multiselect, Direction checkboxes, Call Status checkboxes, Call Type dropdown, Eval Status dropdown, Duration range, Score range
  - Footer: Reset + Apply buttons

- [ ] **Step 3:** Wire into the listing page — "Filters" button toggles the panel.

- [ ] **Step 4:** Commit:
```bash
git add src/features/insideSales/components/CallFilterPanel.tsx
git commit -m "feat: add right-slide filter panel for call listing"
```

---

### Task 6: Call detail drilldown (from listing)

**Files:**
- Create: `src/features/insideSales/pages/InsideSalesCallDetail.tsx`

- [ ] **Step 1:** This follows the `ListingPage.tsx` pattern — back button, page header with badges, metadata grid, audio player, tabs.

- [ ] **Step 2:** Build with:
  - Back button → navigates to listing
  - Header: "Agent → Lead" title + direction/status badges
  - Metadata grid: Date, Agent, Lead, Phone, Duration, Score (if evaluated)
  - `AudioPlayer` component (reuse from `src/features/transcript/`) with recording URL
  - `Tabs` with Transcript and Scorecard (placeholder for now — Phase 5 builds the scorecard)

- [ ] **Step 3:** Register route in `Router.tsx` if not already done:
```typescript
<Route path="/inside-sales/calls/:activityId" element={<InsideSalesCallDetail />} />
```

- [ ] **Step 4:** Commit and verify: clicking a row in the listing navigates to detail, audio plays from S3 URL, back button works.

---

### Task 7: Verify and merge

- [ ] **Step 1:** Full checks:
```bash
npx tsc -b
npm run lint
npm run build
```

- [ ] **Step 2:** End-to-end smoke test:
  - Navigate to Inside Sales → Listing
  - Calls load from LSQ with lead names
  - Pagination works (page 2, 3, etc.)
  - Filter panel opens/closes, filters apply
  - Click a call → detail page with audio player
  - Back to listing preserves filter state

- [ ] **Step 3:** Merge:
```bash
git checkout main
git merge feat/phase-2-lsq-listing
```
