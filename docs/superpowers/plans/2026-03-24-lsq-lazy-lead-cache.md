# LSQ Lazy Lead Cache — Remove Bulk Hydration, Add On-Demand Lead Fetch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the broken bulk lead hydration from the listing flow. Listing shows activity-only fields. Lead details are fetched lazily on detail view via individual `GetById` (reliable, 1:1 mapping), cached in `lsq_call_cache`, with a manual resync button.

**Architecture:** Listing route becomes a simple LSQ activity pass-through (fetch → normalize → filter → return). No lead hydration, no caching on listing. A new `/api/inside-sales/leads/{prospect_id}` endpoint does a single `GetById` call, caches the result in `lsq_call_cache` (repurposed as a lead cache keyed by `prospect_id`), and returns lead details. The detail page calls this endpoint on mount. Resync = same endpoint with `?refresh=true`.

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, httpx, PostgreSQL

---

## File Map

| Action | File | Change |
|--------|------|--------|
| Modify | `backend/app/services/lsq_client.py` | Remove `hydrate_leads_bulk`, `get_cached_calls`, `cache_calls`, `call_cache`. Add `fetch_lead_by_id`. Fix `phoneNumber` mapping. |
| Modify | `backend/app/routes/inside_sales.py` | Simplify `list_calls` (remove cache chain). Add `GET /leads/{prospect_id}` endpoint. Remove `db` dependency from listing. |
| Modify | `backend/app/schemas/inside_sales.py` | Remove `lead_name` from `CallRecord`. Add `LeadDetailResponse` schema. |
| Modify | `backend/app/models/lsq_call_cache.py` | Repurpose as `LsqLeadCache` — keyed by `prospect_id`, stores lead fields only. |
| Modify | `backend/app/models/__init__.py` | Update import for renamed model. |
| Modify | `src/stores/insideSalesStore.ts` | Remove `leadName` from `CallRecord`. |
| Modify | `src/features/insideSales/pages/InsideSalesListing.tsx` | Remove Lead Name + Lead Mobile columns. Remove `leadName` from search filter. |
| Modify | `src/features/insideSales/pages/InsideSalesCallDetail.tsx` | Fetch lead details on mount via new API. Show resync button. |
| Modify | `backend/app/services/evaluators/inside_sales_runner.py` | Remove `get_cached_calls` import, use `fetch_lead_by_id` for lead name in runner. |

---

## Task 1: Repurpose DB Model — `LsqCallCache` → `LsqLeadCache`

**Files:**
- Modify: `backend/app/models/lsq_call_cache.py`
- Modify: `backend/app/models/__init__.py`

The table is repurposed to cache lead data only (not full call records). Keyed by `(tenant_id, prospect_id)` instead of `(tenant_id, activity_id)`.

- [ ] **Step 1: Rewrite the model**

```python
"""Cached LSQ lead data — lazily populated on detail view."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TenantUserMixin


class LsqLeadCache(Base, TenantUserMixin):
    __tablename__ = "lsq_lead_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prospect_id: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "prospect_id", name="uq_lsq_lead_cache_tenant_prospect"),
        Index("idx_lsq_lead_cache_tenant", "tenant_id"),
    )
```

- [ ] **Step 2: Update `__init__.py`**

Replace `LsqCallCache` import with `LsqLeadCache`. Update `__all__`.

- [ ] **Step 3: Drop old table, let new one auto-create**

The old `lsq_call_cache` table has stale data with wrong lead names. Add a `DROP TABLE IF EXISTS lsq_call_cache` in main.py lifespan (before `create_all`), or just let it exist as an orphan. Simpler: add the drop in lifespan since it's a cache table with no critical data.

Check `backend/app/main.py` lifespan for where to add: `await conn.execute(text("DROP TABLE IF EXISTS lsq_call_cache"))` before `Base.metadata.create_all`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/lsq_call_cache.py backend/app/models/__init__.py
git commit -m "refactor: repurpose LsqCallCache → LsqLeadCache (prospect-keyed lead cache)"
```

---

## Task 2: Rewrite `lsq_client.py` — Remove Bulk, Add Individual Lead Fetch

**Files:**
- Modify: `backend/app/services/lsq_client.py`

- [ ] **Step 1: Remove dead code**

Delete these functions entirely:
- `hydrate_leads_bulk` (lines 140-221)
- `get_cached_calls` (lines 224-263)
- `cache_calls` (lines 266-314)

Delete the `call_cache` dict (line 20).

Remove these imports that are no longer needed:
- `uuid`
- `from sqlalchemy import select`
- `from sqlalchemy.ext.asyncio import AsyncSession`
- `from sqlalchemy.dialects.postgresql import insert as pg_insert`

- [ ] **Step 2: Fix `phoneNumber` mapping in `normalize_activity`**

Change line 131 from:
```python
"phoneNumber": source_data.get("DestinationNumber", ""),
```
To:
```python
"phoneNumber": source_data.get("SourceNumber", "") if event_code == 21 else source_data.get("DestinationNumber", ""),
```

For inbound (21): `SourceNumber` = lead's phone. For outbound (22): `DestinationNumber` = lead's phone.

- [ ] **Step 3: Add `fetch_lead_by_id` function**

```python
async def fetch_lead_by_id(prospect_id: str) -> dict[str, str]:
    """Fetch a single lead from LSQ by prospect ID.

    GET /v2/LeadManagement.svc/Leads.GetById?id=<prospectId>
    Returns: {"firstName": str, "lastName": str, "phone": str, "email": str}
    """
    if not prospect_id:
        return {}

    async with httpx.AsyncClient(timeout=30) as client:
        url = f"{LSQ_BASE_URL}/LeadManagement.svc/Leads.GetById"
        params = {**_auth_params(), "id": prospect_id}
        try:
            resp = await _rate_limited_request(client, "GET", url, params=params)
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                lead = data[0]
                return {
                    "firstName": lead.get("FirstName") or "",
                    "lastName": lead.get("LastName") or "",
                    "phone": lead.get("Phone") or "",
                    "email": lead.get("EmailAddress") or "",
                }
        except Exception as e:
            logger.warning("Lead fetch failed for %s: %s", prospect_id, e)

    return {}
```

- [ ] **Step 4: Remove `leadName` from `normalize_activity` return**

Change line 136 from:
```python
"leadName": "",  # Hydrated separately
```
Remove this line entirely — calls no longer carry lead names.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lsq_client.py
git commit -m "refactor: remove bulk hydration, add individual fetch_lead_by_id, fix phoneNumber mapping"
```

---

## Task 3: Simplify Route + Add Lead Endpoint

**Files:**
- Modify: `backend/app/routes/inside_sales.py`
- Modify: `backend/app/schemas/inside_sales.py`

- [ ] **Step 1: Update schema — remove `lead_name`, add `LeadDetailResponse`**

```python
"""Schemas for Inside Sales API."""

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


class CallListResponse(CamelModel):
    calls: list[CallRecord]
    total: int
    page: int
    page_size: int


class LeadDetailResponse(CamelModel):
    prospect_id: str
    first_name: str
    last_name: str
    phone: str
    email: str
    cached: bool = False  # True if served from DB cache
```

- [ ] **Step 2: Simplify `list_calls` route — remove all cache logic**

```python
"""Routes for Inside Sales call data."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.database import get_db
from app.schemas.inside_sales import CallRecord, CallListResponse, LeadDetailResponse
from app.services.lsq_client import fetch_call_activities, normalize_activity, fetch_lead_by_id

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
    """Fetch call activities from LSQ. No lead hydration — listing is activity-only."""
    codes = None
    if event_codes:
        codes = [int(c.strip()) for c in event_codes.split(",")]

    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        event_codes=codes,
        page=page,
        page_size=page_size,
    )

    calls = [normalize_activity(a) for a in result["activities"]]

    if agent:
        calls = [c for c in calls if agent.lower() in c["agentName"].lower()]
    if direction:
        calls = [c for c in calls if c["direction"] == direction]
    if status:
        calls = [c for c in calls if c["status"].lower() == status.lower()]

    return CallListResponse(
        calls=[CallRecord(**c) for c in calls],
        total=result["total"],
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 3: Add lead detail endpoint with DB caching**

```python
@router.get("/leads/{prospect_id}", response_model=LeadDetailResponse)
async def get_lead(
    prospect_id: str,
    refresh: bool = Query(False, description="Force re-fetch from LSQ"),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Fetch lead details by prospect ID. Cached in DB after first fetch.

    Pass ?refresh=true to force re-fetch from LSQ (resync button).
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.lsq_lead_cache import LsqLeadCache
    import uuid as _uuid

    # Check DB cache first (unless refresh requested)
    if not refresh:
        result = await db.execute(
            select(LsqLeadCache).where(
                LsqLeadCache.tenant_id == auth.tenant_id,
                LsqLeadCache.prospect_id == prospect_id,
            )
        )
        cached = result.scalar_one_or_none()
        if cached:
            return LeadDetailResponse(
                prospect_id=prospect_id,
                first_name=cached.first_name,
                last_name=cached.last_name,
                phone=cached.phone,
                email=cached.email,
                cached=True,
            )

    # Fetch from LSQ
    lead = await fetch_lead_by_id(prospect_id)

    # Cache the result (upsert)
    try:
        stmt = pg_insert(LsqLeadCache).values(
            id=_uuid.uuid4(),
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            prospect_id=prospect_id,
            first_name=lead.get("firstName", ""),
            last_name=lead.get("lastName", ""),
            phone=lead.get("phone", ""),
            email=lead.get("email", ""),
        ).on_conflict_do_update(
            constraint="uq_lsq_lead_cache_tenant_prospect",
            set_={
                "first_name": lead.get("firstName", ""),
                "last_name": lead.get("lastName", ""),
                "phone": lead.get("phone", ""),
                "email": lead.get("email", ""),
            },
        )
        await db.execute(stmt)
        await db.commit()
    except Exception:
        await db.rollback()

    return LeadDetailResponse(
        prospect_id=prospect_id,
        first_name=lead.get("firstName", ""),
        last_name=lead.get("lastName", ""),
        phone=lead.get("phone", ""),
        email=lead.get("email", ""),
        cached=False,
    )
```

- [ ] **Step 4: Remove placeholder `get_call` endpoint**

Delete the `/calls/{activity_id}` GET endpoint — it was never implemented and is now replaced by `/leads/{prospect_id}`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/inside_sales.py backend/app/schemas/inside_sales.py
git commit -m "refactor: simplify listing route, add lazy lead endpoint with DB cache"
```

---

## Task 4: Update Frontend — Remove Lead Columns, Add Detail Fetch

**Files:**
- Modify: `src/stores/insideSalesStore.ts`
- Modify: `src/features/insideSales/pages/InsideSalesListing.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesCallDetail.tsx`

- [ ] **Step 1: Remove `leadName` from store `CallRecord` interface**

In `src/stores/insideSalesStore.ts`, remove the `leadName: string;` line from the `CallRecord` interface.

- [ ] **Step 2: Remove Lead Name + Lead Mobile columns from listing table**

In `InsideSalesListing.tsx`:
- Remove `<th>Lead Name</th>` and `<th>Lead Mobile</th>` column headers
- Remove the corresponding `<td>` cells for `call.leadName` and `call.phoneNumber`
- Remove `c.leadName.toLowerCase().includes(q)` and `c.phoneNumber.includes(q)` from the `filteredCalls` search filter
- Keep Prospect ID column (already there)

- [ ] **Step 3: Update `InsideSalesCallDetail` to fetch lead on mount**

The detail page should call `GET /api/inside-sales/leads/{prospectId}` on mount to get lead name/phone. Show a loading state while fetching, then display in the header. Add a "Resync" button that calls the same endpoint with `?refresh=true`.

Read the current `InsideSalesCallDetail.tsx` and add:
- `useState` for lead data + loading state
- `useEffect` to fetch lead on mount
- Display lead name, phone, email in the call detail header
- Small refresh icon button to resync

- [ ] **Step 4: Commit**

```bash
git add src/stores/insideSalesStore.ts src/features/insideSales/pages/InsideSalesListing.tsx src/features/insideSales/pages/InsideSalesCallDetail.tsx
git commit -m "feat: remove lead columns from listing, add lazy lead fetch on call detail"
```

---

## Task 5: Update Runner — Remove `get_cached_calls` Dependency

**Files:**
- Modify: `backend/app/services/evaluators/inside_sales_runner.py`

- [ ] **Step 1: Replace `get_cached_calls` with direct LSQ fetch for specific mode**

The runner's `specific` mode currently uses `get_cached_calls` (which is being deleted). Replace with: for specific mode, always fetch from LSQ activity API. The call IDs are known, fetch activities and filter to matching IDs.

Remove the `get_cached_calls` import. For the `specific` mode block, replace the cache lookup with a direct LSQ fetch (same as the `all/sample` mode but with an ID filter after).

- [ ] **Step 2: Use `fetch_lead_by_id` for lead name in call metadata**

In the section where `call_metadata` is built (around line 357), replace:
```python
"lead": call.get("leadName", "") or call.get("prospectId", ""),
```
With a call to `fetch_lead_by_id`:
```python
lead_data = await fetch_lead_by_id(call.get("prospectId", ""))
lead_name = f"{lead_data.get('firstName', '')} {lead_data.get('lastName', '')}".strip() or call.get("prospectId", "")[:8]
```
And use `lead_name` in the metadata.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/evaluators/inside_sales_runner.py
git commit -m "refactor: runner uses fetch_lead_by_id instead of cache, direct LSQ for specific mode"
```

---

## Task 6: Clean Up — Drop Old Table

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add table drop in lifespan**

In the lifespan's `create_all` block, add before `Base.metadata.create_all`:
```python
await conn.execute(text("DROP TABLE IF EXISTS lsq_call_cache"))
```

Import `text` from `sqlalchemy` if not already imported.

- [ ] **Step 2: Verify stack starts cleanly**

```bash
docker compose up --build
```

Check: no import errors, old table dropped, new `lsq_lead_cache` table created.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "chore: drop orphaned lsq_call_cache table on startup"
```

---

## Task 7: Smoke Test

- [ ] **Step 1: Verify listing loads without lead columns**

Load Inside Sales listing — should show activity-only data. No 429 errors. No lead name or phone columns.

- [ ] **Step 2: Click a call row → verify lead fetch**

Click into a call detail. The detail page should:
- Show a brief loading state
- Fetch lead data from `/api/inside-sales/leads/{prospectId}`
- Display lead name + phone in the header

- [ ] **Step 3: Click resync → verify fresh fetch**

Click the resync button. Backend logs should show a fresh `GetById` call. Data should update.

- [ ] **Step 4: Navigate back and re-enter → verify cache hit**

Go back to listing, click the same call. This time: backend should serve from DB cache (no LSQ call). Response should have `cached: true`.

- [ ] **Step 5: Verify phoneNumber fix**

Check that inbound calls show the lead's actual phone (from `SourceNumber`), not the agent's extension.

---

## Summary of Changes

| Before | After |
|--------|-------|
| Listing hydrates all leads via bulk API (broken, wrong names) | Listing shows activity data only — zero lead API calls |
| Bulk endpoint can't match IDs (no ProspectId in response) | Individual GetById — reliable 1:1 mapping |
| Cache stores full call records | Cache stores lead data only (smaller, correct) |
| Lead name shown in listing table | Lead name shown in detail view (fetched on demand) |
| `phoneNumber` = `DestinationNumber` (wrong for inbound) | `phoneNumber` = `SourceNumber` for inbound, `DestinationNumber` for outbound |
| ~200 lines of bulk hydration + cache chain code | ~30 lines for individual fetch + simple cache |
