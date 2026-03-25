# AI Concierge — Design Specification

**Feature:** Automated lead engagement via WhatsApp (WATI) + AI voice (Bolna) orchestrated from the Inside Sales platform
**Status:** Design / Pre-implementation
**Scope:** Inside Sales feature (`src/features/insideSales/`)

---

## 1. Problem Statement

Inside Sales operates at ~150 dials/day yielding only 5–6 counseling sessions (~3.3% conversion). Root causes:

- **After-hours leads** (~30–40%) receive no response until next business day
- **Low-MQL leads** consume agent bandwidth that belongs to high-intent prospects
- **RNR loops** — leads go unanswered 8–12 times before a human touches them meaningfully

The AI Concierge intercepts leads before human agents, qualifies them via WhatsApp, books slots, and runs confirmation calls via Bolna — reserving agents for counseling-ready conversations only.

---

## 2. Triage Logic

### 2.1 MQL Signal Set (existing, no changes)

The five binary signals already computed server-side in `LeadListRecord.mqlSignals`:

| Signal key | Criteria |
|---|---|
| `age` | Age group in 25–65 range |
| `city` | Lead city in target city list |
| `condition` | Qualifying condition (T2D, pre-diabetes, obesity) |
| `hba1c` | HbA1c band reported |
| `intent` | Intent to pay field present and positive |

`mqlScore` = count of `true` signals (0–5). Already in the API.

### 2.2 Routing Tiers

| Tier | Score | Label | WA Template | Bolna Action |
|---|---|---|---|---|
| **High** | 4–5 | Priority Lane | Slot-booking with personalized HbA1c/city | Auto-schedule confirmation call on slot reply |
| **Mid** | 2–3 | Qualify Lane | Warm qualify — health goal + preferred time | Schedule call only if WA reply confirms interest |
| **Low** | 0–1 | Nurture Lane | Collect missing profile fields | No Bolna; re-score after reply |

### 2.3 Timing Flags (applied on top of tier)

Two modifiers that influence which WA template variant fires:

- **After-hours flag** — `createdOn` outside 8 AM–8 PM IST → template variant emphasizes "reply at your convenience"
- **Stale flag** — `daysSinceLastContact > 7` → RNR revival template ("haven't been able to reach you")
- **Callback adherence breach** — `callbackAdherenceSeconds > 3600` → apology + re-book template

These are computed at trigger time from existing `LeadListRecord` fields — no new signals needed.

### 2.4 Eligibility Gate

A lead is eligible for AI Concierge if **all** of the following are true:

1. `prospectStage` is not in terminal set: `{'not interested', 'converted', 'invalid / junk'}`
2. No active `concierge_action` in state `wa_sent`, `bolna_queued`, or `bolna_running` for this lead
3. Lead has not been manually excluded (per-tenant config flag, spec'd in §5.3)

---

## 3. Full Flow Sequence

```
Lead arrives / re-scored
        │
        ▼
[Eligibility Gate] ──✗──▶ Skip (no action)
        │ ✓
        ▼
[Compute Tier + Timing Flags]
        │
        ▼
[Select WA Template]  ◀── template registry in DB (§5.2)
        │
        ▼
POST /wati/send-template
        │
        ├──▶ Delivery failure ──▶ log action(wa_failed), stop
        │
        ▼
action: wa_sent  →  wait for WATI webhook
        │
        ├── No reply within N hours (configurable) ──▶ [Fallback Bolna call] (if tier ≥ High)
        │
        ├── Reply = slot confirmation ──▶ [Schedule Bolna confirmation call]
        │         │
        │         ▼
        │   POST /bolna/call  →  action: bolna_queued
        │         │
        │         ▼
        │   Bolna webhook (completed)
        │         │
        │         ├── Answered + slot confirmed ──▶ action: handoff_queued
        │         │         │
        │         │         ▼
        │         │   Update LSQ stage → "Slot Confirmed"
        │         │   Notify assigned agent (WS push)
        │         │
        │         └── RNR / no answer ──▶ action: bolna_rnr
        │                   │
        │                   └── Retry once after 2h (config) ──▶ re-queue Bolna job
        │
        └── Reply = not interested ──▶ action: wa_declined, stop
```

---

## 4. Data Model

### 4.1 New table: `concierge_actions`

Each row is one atomic orchestration event for a lead. Append-only log — never update rows, only insert new state transitions.

```python
class ConciergeAction(Base, TenantUserMixin):
    __tablename__ = "concierge_actions"

    id: UUID (PK)
    tenant_id: UUID (FK → tenants, NOT NULL)
    user_id: UUID (FK → users, NOT NULL)          # user who triggered or "system" for auto
    prospect_id: str (NOT NULL, indexed)           # LSQ prospect ID
    triggered_by: Literal["manual", "auto"]
    action_type: ConciergeActionType               # enum below
    channel: Literal["wa", "bolna", "system"]
    status: Literal["pending", "success", "failed"]
    payload: JSONB                                 # request payload sent to provider
    response: JSONB                                # provider response / webhook payload
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    job_id: UUID | None (FK → jobs)                # links to background job if async
```

**`ConciergeActionType` enum:**

```python
class ConciergeActionType(str, Enum):
    wa_dispatched       = "wa_dispatched"
    wa_delivered        = "wa_delivered"
    wa_read             = "wa_read"
    wa_replied          = "wa_replied"
    wa_declined         = "wa_declined"
    wa_failed           = "wa_failed"
    wa_no_reply_timeout = "wa_no_reply_timeout"
    bolna_queued        = "bolna_queued"
    bolna_answered      = "bolna_answered"
    bolna_rnr           = "bolna_rnr"
    bolna_failed        = "bolna_failed"
    handoff_queued      = "handoff_queued"
    triage_skipped      = "triage_skipped"
```

### 4.2 Derived: latest concierge state per lead

Not a table — a computed view / aggregation query. Backend returns the **latest** `action_type` + `status` per `prospect_id` as `conciergeStatus` in `LeadListRecord` and `LeadDetailFullResponse`.

```typescript
// Extend existing types in src/services/api/insideSales.ts

export type ConciergeState =
  | 'idle'
  | 'wa_sent'
  | 'slot_confirmed'
  | 'bolna_scheduled'
  | 'completed'
  | 'no_reply'
  | 'declined';

export interface ConciergeStatusSummary {
  state: ConciergeState;
  label: string;             // human-readable, e.g. "WA Sent · 14m ago"
  lastActionAt: string | null;
  tier: 'high' | 'mid' | 'low';
}

// Add to LeadListRecord:
conciergeStatus: ConciergeStatusSummary | null;

// Add to LeadDetailFullResponse:
conciergeStatus: ConciergeStatusSummary | null;
conciergeActions: ConciergeActionResponse[];   // full log for detail view
```

### 4.3 New table: `concierge_templates`

Stores WA template configurations per tenant + tier + timing variant. Allows tenant-level customisation without code changes.

```python
class ConciergeTemplate(Base):
    __tablename__ = "concierge_templates"

    id: UUID (PK)
    tenant_id: UUID (FK → tenants)          # NULL = system default (read by all tenants)
    tier: Literal["high", "mid", "low"]
    timing_variant: Literal["standard", "after_hours", "stale", "callback_breach"]
    wati_template_name: str                 # Meta-approved template name on WATI account
    variable_map: JSONB                     # maps template placeholders → LeadListRecord fields
                                            # e.g. {"1": "firstName", "2": "city", "3": "hba1cBand"}
    bolna_agent_id: str | None              # Bolna agent to use for this tier
    bolna_script_id: str | None
    active: bool
```

### 4.4 New table: `concierge_config`

Per-tenant feature flags and thresholds. One row per tenant.

```python
class ConciergeConfig(Base):
    __tablename__ = "concierge_config"

    tenant_id: UUID (PK, FK → tenants)
    enabled: bool = True
    no_reply_timeout_hours: int = 4         # hours before fallback Bolna fires
    bolna_retry_count: int = 1
    bolna_retry_delay_hours: int = 2
    excluded_stages: list[str]              # additional stages to skip beyond system defaults
    auto_trigger_on_new_lead: bool = False  # future: auto-trigger on LSQ webhook
```

---

## 5. Backend — Orchestration Engine

### 5.1 New router: `concierge.py`

Prefix: `/api/concierge` — requires `auth:AuthContext` on every route.

```
POST   /api/concierge/trigger            # Manual trigger for a lead
GET    /api/concierge/actions            # Paginated action log (tenant-scoped)
GET    /api/concierge/actions/{id}       # Single action detail
POST   /api/concierge/webhooks/wati      # WATI inbound webhook (public — verified by HMAC)
POST   /api/concierge/webhooks/bolna     # Bolna completion webhook (public — verified by secret)
GET    /api/concierge/config             # Fetch tenant config
PATCH  /api/concierge/config             # Update tenant config
GET    /api/concierge/templates          # List templates (system + tenant overrides)
```

### 5.2 New job handler: `orchestrate_concierge`

Fits the existing `job_worker.py` dispatch pattern. Add to the handler registry alongside `evaluate-voice-rx`, `evaluate-batch`, etc.

```python
# backend/app/services/jobs/concierge_handler.py

JOB_TYPE = "orchestrate-concierge"

async def run(job: Job, db: AsyncSession) -> None:
    params = job.params
    action_type = params["action_type"]   # "trigger_wa" | "schedule_bolna" | "retry_bolna"
    prospect_id = params["prospect_id"]
    tenant_id   = params["tenant_id"]
    user_id     = params["user_id"]

    if action_type == "trigger_wa":
        await _dispatch_wa(prospect_id, tenant_id, user_id, params, db)
    elif action_type == "schedule_bolna":
        await _schedule_bolna(prospect_id, tenant_id, user_id, params, db)
    elif action_type == "retry_bolna":
        await _retry_bolna(prospect_id, tenant_id, user_id, params, db)
```

Cancellation: call `is_job_cancelled(job.id)` before each network call — existing pattern, no changes needed.

### 5.3 New service: `WatiService`

```python
# backend/app/services/wati_service.py

class WatiService:
    """Thin wrapper over WATI REST API. All methods are async."""

    def __init__(self, api_token: str, base_url: str): ...

    async def send_template(
        self,
        phone: str,                        # E.164 format
        template_name: str,
        broadcast_name: str,
        parameters: list[dict],            # [{"name": "1", "value": "Priya"}, ...]
    ) -> WatiSendResponse: ...

    async def get_conversation(
        self,
        wa_id: str,                        # WATI conversation ID from send response
    ) -> WatiConversation: ...
```

Credentials read from `settings` table using existing `get_app_settings()` pattern — keys `wati_api_token`, `wati_base_url` scoped to tenant. **Never hardcoded.**

### 5.4 New service: `BolnaService`

```python
# backend/app/services/bolna_service.py

class BolnaService:
    """Thin wrapper over Bolna REST API."""

    def __init__(self, api_key: str, base_url: str): ...

    async def place_call(
        self,
        agent_id: str,
        recipient_phone: str,              # E.164
        user_data: dict,                   # variables injected into Bolna script
        retry_config: dict | None = None,  # {"max_retries": 1, "retry_wait": 120}
        scheduled_at: datetime | None = None,
    ) -> BolnaCallResponse: ...            # returns execution_id
```

Credentials from `settings` table — keys `bolna_api_key`, `bolna_base_url`.

### 5.5 Webhook receivers

Both are **public routes** (no Bearer token) but must verify authenticity:

- **WATI**: HMAC-SHA256 signature header `x-wati-signature` against body + shared secret
- **Bolna**: `x-bolna-secret` header matches configured value

On receipt:
1. Verify signature — reject 400 if invalid
2. Parse event type (`sentMessageREPLIED`, `message` for WATI; `completed` for Bolna)
3. Insert `ConciergeAction` row for the event
4. If event triggers next step (e.g. slot reply → schedule Bolna), submit a new job via the existing job submission path

---

## 6. Frontend — Components

### 6.1 Reuse (no changes to existing)

| Existing component | Used where |
|---|---|
| `Badge` (`src/components/ui/Badge.tsx`) | `ConciergeStatusBadge` wraps it with concierge-specific variants |
| `MqlScoreBadge` | Reused as-is in `ConciergeDrawer` signal breakdown |
| `StageBadge` | Reused as-is throughout |
| `Tabs` | Lead detail — add new tab item; `Tabs` component unchanged |
| `Button` | All CTAs |
| `Tooltip` | Column headers, signal labels |
| `EmptyState` | No-actions state in log view and AI Concierge tab |
| `Spinner` | Loading states |
| `Modal` | Confirm dialog before triggering on leads with active WA threads |
| `Card` | Wrap `WaThreadView` and `BolnaCallCard` sections |
| `CallResultPanel` | Bolna call result (eval score) reuses this if we run evaluation on Bolna recording |

### 6.2 New components (inside `src/features/insideSales/components/`)

#### `ConciergeStatusBadge.tsx`

Thin wrapper around `Badge` that maps `ConciergeState` → variant + label. Single source of truth for status rendering in table column, drawer header, and detail tab.

```typescript
interface ConciergeStatusBadgeProps {
  status: ConciergeStatusSummary;
  showDot?: boolean;   // default true
  size?: 'sm' | 'md';
}

// Variant map (no hardcoded colours — all use Badge variants):
const STATE_TO_VARIANT: Record<ConciergeState, BadgeVariant> = {
  idle:            'neutral',
  wa_sent:         'info',
  slot_confirmed:  'success',
  bolna_scheduled: 'primary',
  completed:       'warning',    // amber — awaiting human follow-up
  no_reply:        'error',
  declined:        'neutral',
};
```

#### `ConciergeDrawer.tsx`

Slide-in right panel triggered from the leads table. Replaces the inline mockup approach with a proper component.

```typescript
interface ConciergeDrawerProps {
  lead: LeadListRecord;
  open: boolean;
  onClose: () => void;
  onTriggered: () => void;  // callback to refresh row after submission
}
```

Internal sections (each a sub-component):

- `MqlTierCard` — reads `mqlScore` + `mqlSignals`, renders tier label + signal breakdown. Reuses `MqlScoreBadge`.
- `WaTemplatePreview` — fetches matching template from `/api/concierge/templates?tier=X&variant=Y`, renders interpolated preview. Uses `SearchableSelect` from UI lib for template override.
- `BolnaScheduleForm` — time picker + toggle. Conditionally rendered based on tier.
- Submit calls `POST /api/concierge/trigger` → creates a `Job` → existing `submitAndPollJob()` pattern.

**Do not** custom-poll in the component. Submit job, show toast, refresh via `useLeadsStore.getState().loadLeads()`.

#### `ConciergeTab.tsx`

Content for the **AI Concierge** tab inside `InsideSalesLeadDetail`. Composed of:

- `MqlTierCard` (same component as above — reused)
- `WaThreadView` — renders `conciergeActions` filtered to WA channel as a chat bubble list
- `BolnaCallCard` — renders Bolna call result; hooks into `CallResultPanel` if eval score is present
- Trigger button (when `conciergeStatus.state === 'idle'`) — opens `ConciergeDrawer` in-context

#### `WaThreadView.tsx`

```typescript
interface WaThreadViewProps {
  actions: ConciergeActionResponse[];   // filtered to channel === 'wa'
}
```

Renders each action as a message bubble — outbound (platform → lead) or inbound (lead reply parsed from WATI webhook payload). Uses existing CSS variable tokens; no hardcoded colours.

#### `BolnaCallCard.tsx`

```typescript
interface BolnaCallCardProps {
  action: ConciergeActionResponse;       // action_type in {bolna_answered, bolna_rnr, bolna_failed}
  evalResult?: ThreadEvalRow | null;     // if recording was evaluated, pass here → CallResultPanel
}
```

Shows: call time, duration, outcome badge, transcript (from `action.response.transcript`). If `evalResult` is provided, renders `CallResultPanel` beneath.

#### `ConciergeLogTable.tsx`

New tab on `InsideSalesListing` — **Orchestration Log**. Shows all `ConciergeAction` rows for the tenant, paginated, filterable by channel / action_type / date. Follows the exact same table pattern as `LeadsTableContent`.

```typescript
// Column set:
// Time | Lead | Channel | Action | Status | Triggered by | Details (expand)
```

Reuses:
- Existing table markup pattern (`table`, `thead sticky`, `tbody tr hover`)
- `StageBadge` for lead stage in the Lead cell
- `MqlScoreBadge` for MQL inline
- `ConciergeStatusBadge` for Action column

---

## 7. Frontend — Store & API Layer

### 7.1 No new Zustand store

Concierge state is per-lead, not global. Co-locate with the existing `insideSalesStore`:

```typescript
// Add to src/stores/insideSalesStore.ts

interface InsideSalesStore {
  // ... existing fields ...

  // Orchestration log (for ConciergeLogTable)
  conciergeLog: ConciergeActionResponse[];
  conciergeLogTotal: number;
  conciergeLogPage: number;
  conciergeLogLoading: boolean;
  conciergeLogError: string | null;
  loadConciergeLog: () => Promise<void>;
  setConciergeLogPage: (page: number) => void;
}
```

### 7.2 New API service: `src/services/api/concierge.ts`

Uses `apiRequest` — no raw fetch.

```typescript
export async function triggerConcierge(
  prospectId: string,
  overrides?: { templateId?: string; scheduledAt?: string }
): Promise<JobResponse>

export async function fetchConciergeActions(
  params: { page: number; pageSize: number; channel?: string; actionType?: string; dateFrom?: string; dateTo?: string }
): Promise<{ actions: ConciergeActionResponse[]; total: number }>

export async function fetchLeadConciergeActions(
  prospectId: string
): Promise<ConciergeActionResponse[]>

export async function fetchConciergeConfig(): Promise<ConciergeConfigResponse>
export async function updateConciergeConfig(
  patch: Partial<ConciergeConfigResponse>
): Promise<ConciergeConfigResponse>
```

---

## 8. UI Information Architecture

### 8.1 Inside Sales Listing — Leads tab

```
[Search] [Filters] ················· [AI Concierge ○●] ← tenant toggle (persisted to config)

| Lead | Stage | MQL | Owner | Dials | Connect % | FRT | Last Contact | AI Status ⊕ NEW |   |
|──────|───────|─────|───────|───────|───────────|─────|──────────────|─────────────────|───|
| row  |  ...  |     |       |       |           |     |              | <ConciergeStatusBadge> | [Trigger AI →] hover |
```

- `AI Status` column is conditionally hidden when `conciergeConfig.enabled === false`
- `[Trigger AI →]` button appears on row hover only — does not clutter default view
- Clicking the button: opens `ConciergeDrawer` (does not navigate away)
- Clicking the row: navigates to lead detail (existing behaviour, no change)

### 8.2 Inside Sales Listing — new tab: Orchestration Log

Added as a third tab on `InsideSalesListing` (after Leads, All Calls):

```
[Leads] [All Calls] [Orchestration Log ✦]

Filters: [Channel ▾] [Status ▾] [Date range]   [Export CSV]

| Time | Lead | Channel | Action | Status | Triggered by | — |
```

Channel column uses channel-specific icons (WA green dot, phone icon for Bolna). Expand row → shows `payload` + `response` JSON in a collapsible pre block (same as existing eval detail expansions).

### 8.3 Lead Detail — AI Concierge tab

Tab order: `Call Timeline` · `Evaluations` · `AI Concierge ✦`

Tab content layout (top-down, scrollable):

```
┌─ MQL Tier ─────────────────────────────────────────────────┐
│  [MqlTierCard] — score, tier label, signal breakdown        │
└────────────────────────────────────────────────────────────┘

┌─ WhatsApp Thread ──────────────────────────────────────────┐
│  [WaThreadView] — chat bubbles, timestamps, delivery status │
└────────────────────────────────────────────────────────────┘

┌─ AI Voice Calls ───────────────────────────────────────────┐
│  [BolnaCallCard] × N — one card per Bolna action            │
│  If evaluated: [CallResultPanel] inside card                │
└────────────────────────────────────────────────────────────┘

[Trigger AI Concierge] ← only if state === 'idle'
```

---

## 9. Settings & Config Surface

### 9.1 Credentials (per-tenant, stored in `settings` table)

| Key | Description |
|---|---|
| `wati_api_token` | WATI Bearer token |
| `wati_base_url` | WATI API base URL (varies by region) |
| `wati_webhook_secret` | HMAC secret for verifying inbound webhooks |
| `bolna_api_key` | Bolna API key |
| `bolna_base_url` | Bolna API base (default: `https://api.bolna.dev`) |
| `bolna_webhook_secret` | Secret for verifying Bolna completion webhooks |

Stored via existing `PATCH /api/settings` endpoint — no new route needed. Never committed to code.

### 9.2 Admin UI (future, not in v1)

`ConciergeConfig` fields (`no_reply_timeout_hours`, `bolna_retry_count`, etc.) surfaced in the Settings page — tab: `AI Concierge`. Uses existing `LLMConfigSection` layout pattern from `src/components/ui/LLMConfigSection.tsx` as a visual reference.

---

## 10. Permissions

Reuses existing RBAC. No new permissions in v1 — `eval:run` covers trigger actions. Consider adding `concierge:trigger` and `concierge:config` as separate permissions in a future RBAC iteration for finer control.

---

## 11. Invariants

1. `concierge_actions` is **append-only**. Never UPDATE a row after insert.
2. Eligibility gate must check for active actions **before** submitting a new trigger job, even in manual trigger flows — prevents double-dispatch races.
3. WATI and Bolna credential lookups must go through `get_app_settings()` — never read from environment or hardcode.
4. Bolna webhook handler must call `is_job_cancelled()` before processing — job may have been cancelled mid-flight.
5. `WaThreadView` renders from `ConciergeActionResponse.payload/response` — no separate WA conversation store.
6. The `ConciergeStatusBadge` is the single source of truth for state → colour mapping. Do not replicate the mapping in table cells, drawer headers, or detail views.

---

## 12. Implementation Sequence

| Phase | Scope | Branch |
|---|---|---|
| **1 — Data layer** | Alembic migration: `concierge_actions`, `concierge_templates`, `concierge_config`. Schemas + models. Seed default templates. | `feat/concierge-data` |
| **2 — Backend services** | `WatiService`, `BolnaService`, `concierge_handler.py` job. Webhook receivers. Router `/api/concierge`. | `feat/concierge-backend` |
| **3 — Leads table** | Extend `LeadListRecord` with `conciergeStatus`. Add AI Status column + trigger button. `ConciergeStatusBadge`. | `feat/concierge-table` |
| **4 — Drawer** | `ConciergeDrawer` + `MqlTierCard` + `WaTemplatePreview` + `BolnaScheduleForm`. | `feat/concierge-drawer` |
| **5 — Detail tab** | `ConciergeTab` + `WaThreadView` + `BolnaCallCard`. | `feat/concierge-detail` |
| **6 — Log view** | `ConciergeLogTable` as new listing tab. Filter + pagination. | `feat/concierge-log` |
| **7 — Settings** | Credential entry in Settings UI. `ConciergeConfig` admin panel. | `feat/concierge-settings` |
