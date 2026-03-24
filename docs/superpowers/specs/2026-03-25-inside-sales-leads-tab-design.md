# Inside Sales — Leads Tab & Lead Drilldown Design Spec

**Date:** 2026-03-25
**Scope:** New "Leads" tab on the Inside Sales listing page + lead drilldown with call timeline and embedded eval
**Context:** Derived from VP of Inside Sales discovery session and LSQ API investigation (live API calls confirmed)

---

## 1. Background & Motivation

The existing Inside Sales listing shows one row per **call activity** (LSQ event codes 21/22). This is useful for QA sampling but gives no view of the **lead journey** — how many attempts were made, whether the lead is qualified, where it sits in the funnel, and what the overall engagement looks like across all calls.

The VP described three key pain points this addresses:
1. No way to see funnel state across all leads in one view — managers manually filter LSQ and run Excel
2. No lead quality signal — all 100 leads get identical effort regardless of qualification
3. No per-lead counseling/SLA visibility without listening to individual calls

This spec adds a **Leads tab** (prospect-centric, one row per lead) to the existing listing page, and a **Lead Drilldown** that shows the full lead journey with embedded eval results.

---

## 2. LSQ Data Source — Confirmed Fields

Verified via live API calls to `api-in21.leadsquared.com/v2` on 2026-03-25.

### Lead record fields (`LeadManagement.svc/Leads.Get`)

| Field | Content |
|---|---|
| `ProspectID` | UUID — primary key |
| `FirstName`, `LastName` | Lead name |
| `Phone`, `EmailAddress` | Contact |
| `ProspectStage` | Current funnel stage (see Section 3.1) |
| `mx_City` | City from form |
| `mx_Age_Group` | Age band, e.g. "41–50" |
| `mx_utm_disease` | Condition: "Diabetes", "PCOS", etc. |
| `mx_Do_you_remember_your_HbA1c_levels` | Self-reported HbA1c band |
| `mx_Do_you_know_your_recent_blood_sugar_level` | Self-reported blood sugar band |
| `mx_Are_you_open_to_investing_in_this_paid_program_of` | Intent to pay (free-text option) |
| `mx_Diabetes_Duration` | How long diagnosed |
| `mx_Current_diabetes_management` | Current treatment approach |
| `mx_What_is_your_main_health_goal` | Primary goal |
| `mx_Job_Title_or_Occupation` | Occupation |
| `mx_Preferred_Time_for_Call_with_Health_Counsellor` | Stated preferred callback time |
| `mx_RNR_Count` | LSQ-maintained RNR counter (may be null for brand-new leads) |
| `mx_Answered_Call_Count` | LSQ-maintained answered call counter (may be null) |
| `mx_Lead_Status` | Custom status (Warm/Hot/Cold) |
| `CreatedOn` | Lead creation timestamp |
| `ProspectActivityDate_Min` | First activity timestamp (proxy for first call — see Section 3.4) |
| `ProspectActivityDate_Max` | Last activity timestamp (null if no activity yet) |
| `OwnerIdName` | Assigned agent name (may be null for unassigned leads) |
| `Source`, `SourceCampaign` | Marketing source |

### Per-lead call history (activity API)

No native per-lead activity history endpoint exists in this LSQ instance (confirmed: 404 on all candidate endpoints).

**Strategy (drilldown only):** `POST /ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent` with:
- Event codes `[21, 22]` (inbound + outbound)
- Date range `[lead.CreatedOn, now]`
- `PageSize: 500` per page, iterate if `RecordCount > 500`
- Server-side filter: keep only records where `RelatedProspectId == prospect_id`

**Known limitation:** The LSQ API may impose undocumented result caps or rate limits on very wide date ranges (e.g., leads created 2+ years ago). If `RecordCount` from the API response exceeds the number of records returned, the implementer must paginate. If pagination is still incomplete (RecordCount > 500 × pages fetched), the drilldown must display a warning: "Call history may be incomplete — LSQ returned N of M records." Metrics derived from incomplete history (FRT, counseling count) must NOT be shown in this case.

Call history is never fetched for the listing — only on drilldown.

---

## 3. Math & Metrics Definitions

All metrics are deterministic. No inference or estimation.

### 3.1 Lead Stage Values & Colors

| LSQ `ProspectStage` | Display label | Color |
|---|---|---|
| New Lead | New | gray |
| Call Back | Callback | amber |
| RNR | RNR | orange |
| Interested in future plan | Interested | blue |
| Not Interested | Not Interested | red |
| Converted | Converted | green |
| Invalid / Junk | Junk | gray (muted) |
| Re-enquired | Re-enquired | purple |
| (any unrecognised value) | raw value | gray |

### 3.2 MQL Signal Score (0–5)

Each signal is binary (1 or 0). Sum = MQL score. No weighting — weights require empirical per-signal conversion data that does not yet exist. Upgrade to logistic regression once 3–6 months of conversion data is available per the VP's request.

| Signal | Field | Condition for 1 | Research basis |
|---|---|---|---|
| **Age in range** | `mx_Age_Group` | Band overlaps 30–65 (see mapping below) | Digital health program adherence peaks 35–60; <30 low diabetes burden; >65 low remote-program adoption |
| **City in target list** | `mx_City` | In configured target city list (default: VP's top 25, stored server-side) | Proxy for disposable income + broadband + remote-care comfort |
| **Condition relevant** | `mx_utm_disease` | Diabetes / PCOS / Fatty Liver / Obesity / Hypertension | Direct product fit |
| **HbA1c ≥ 5.7%** | `mx_Do_you_remember_your_HbA1c_levels` | Any reported band ≥ 5.7 | ADA 2024: ≥5.7 = clinical intervention indicated (pre-diabetes or above) |
| **Intent not negative** | `mx_Are_you_open_to_investing_in_this_paid_program_of` | Non-null AND value does not contain "no" (case-insensitive) | Direct purchase intent signal from intake form |

**MQL thresholds:**
- Score = 5 → MQL (green badge)
- Score = 4 → Near-MQL (amber badge)
- Score ≤ 3 → Not qualified (gray badge)

Null/blank field values always yield 0 for that signal — never inferred.

**Age band mapping:**

| `mx_Age_Group` | Signal = 1? | Notes |
|---|---|---|
| Under 30 / 18–30 | No | |
| 31–40 | Yes | |
| 41–50 | Yes | |
| 51–60 | Yes | |
| 61–65 | Yes | Exactly in range |
| 61–70 | Yes | Band straddles upper bound. Treat as 1 — conservative inclusion. If LSQ adds a 61–65 band later, update. |
| 71+ / Above 70 | No | |
| null / blank | No | |

### 3.3 Call Efficiency Metrics

Null LSQ counter fields (`mx_RNR_Count`, `mx_Answered_Call_Count`) are treated as 0.

| Metric | Formula | Source | Edge case |
|---|---|---|---|
| **RNR count** | `int(mx_RNR_Count or 0)` | Lead record | Null → 0 |
| **Answered count** | `int(mx_Answered_Call_Count or 0)` | Lead record | Null → 0 |
| **Total dials** | `rnr_count + answered_count` | Derived | `CallFailure` excluded (system errors, not agent dials) |
| **Connect rate** | `answered_count / total_dials × 100` | Derived | `None` (→ `—`) when `total_dials == 0` |
| **Lead age (days)** | `⌊(now − CreatedOn) / 86400⌋` | `CreatedOn` | Integer days; `CreatedOn` is always present |
| **Days since last contact** | `⌊(now − ProspectActivityDate_Max) / 86400⌋` | `ProspectActivityDate_Max` | `None` (→ `—`) when field is null (no activity yet) |

### 3.4 First Response Time (FRT)

**Definition:** Time between lead creation and the first human outbound call attempt.

**Listing — proxy FRT:**
```
frt_seconds = (ProspectActivityDate_Min − CreatedOn).total_seconds()
```
`ProspectActivityDate_Min` is the first *activity* on the record, which is the first call in practice. Used as a proxy because fetching call history in the listing is too expensive.

**Drilldown — exact FRT:**
```
first_call_time = min(c.call_time for c in call_history)
frt_seconds = (first_call_time − CreatedOn).total_seconds()
```

**Both cases:**
- If result < 0 (LSQ clock skew or data import artefact): `frt_seconds = None` (→ `—`). Do not display a negative FRT.
- If `ProspectActivityDate_Min` is null (listing) or `call_history` is empty (drilldown): `frt_seconds = None` (→ `—`).

**Display thresholds (applies to both proxy and exact):**
- `frt_seconds ≤ 3600` → green (`< 1h` or `Xm Ys`)
- `3600 < frt_seconds ≤ 10800` → amber
- `frt_seconds > 10800` → red
- `None` → `—` (no color)

### 3.5 Counseling Sessions (drilldown only)

VP definition: a meaningful counseling session requires ≥ 10 minutes of conversation.

In the drilldown, `total_answered_from_history` = `count(c for c in call_history if c.status == "Answered")`. This is derived from the fetched call history, not from `mx_Answered_Call_Count`, because the two sources must be consistent for the counseling rate denominator.

```
counseling_count = count(c for c in call_history if c.duration_seconds >= 600)

counseling_rate = (counseling_count / total_answered_from_history × 100)
                  if total_answered_from_history > 0
                  else None
```

`counseling_rate` is `None` (→ `—`) when `total_answered_from_history == 0`.

### 3.6 Callback Adherence (drilldown only, conditional)

Only computed and shown when `mx_Preferred_Time_for_Call_with_Health_Counsellor` is non-null.

```
preferred_time = parse(mx_Preferred_Time_for_Call_with_Health_Counsellor)
first_call_after_pref = min(
    c.call_time for c in call_history if c.call_time > preferred_time,
    default=None
)

if first_call_after_pref is not None:
    adherence_delta_seconds = (first_call_after_pref − preferred_time).total_seconds()
else:
    adherence_delta_seconds = None  # no call ever placed after preferred time
```

Display: "Called Xh Ym after preferred time". Not shown if `adherence_delta_seconds` is None.

Note: calling *before* the preferred time is also a miss (lead may be unavailable). Delta is measured forward from the preferred time only — early calls are not rewarded.

---

## 4. Leads Tab — Listing

### Tab order

```
[ Leads ]  [ All Calls ]
```

Leads is index 0 (rendered first). Switching tabs preserves shared date range and agent filter state.

### Table columns

Same component and style as the existing call table. No new table primitives.

| # | Column | Source | Display |
|---|---|---|---|
| 1 | **Lead** | `FirstName + LastName` / `Phone` | Name bold, phone mono below in muted |
| 2 | **Stage** | `ProspectStage` | Color-coded badge (Section 3.1) |
| 3 | **MQL** | Computed (Section 3.2) | `4/5` + 5 signal dots (●●●●○). Hover tooltip shows per-signal breakdown |
| 4 | **Agent** | `OwnerIdName` | Plain text. `—` if null |
| 5 | **Dials** | `mx_RNR_Count + mx_Answered_Call_Count` | Integer. `—` if both null |
| 6 | **Connect %** | `answered / dials × 100` | `42%`. `—` if dials = 0 |
| 7 | **FRT** | `ProspectActivityDate_Min − CreatedOn` (proxy) | `< 1h` / `2h 15m` / `1d 4h`. Color by threshold. `—` if null or negative |
| 8 | **Last Contact** | `now − ProspectActivityDate_Max` | `Today` / `2d ago`. `—` if null. Red if > 7d and stage is not a terminal stage |

Sortable: Stage, MQL, Dials, Connect %, FRT, Last Contact.

**No Eval column in the listing.** `ThreadEvaluation` records are keyed by `thread_id = activityId` (per-call). The listing has no call-level data — there is no correct way to join evals to leads without fetching call history, which is too expensive for the listing. Eval data is available in the drilldown only.

### MQL dot tooltip (hover on MQL cell)

```
● Age 41–50           ✓
● City: Hyderabad     ✓
● Condition: Diabetes ✓
● HbA1c: 5.7–6.4     ✓
○ Intent: unclear     ✗
```

### Filter panel (Leads tab)

Right-slide overlay, same `CallFilterPanel` pattern. Leads-specific filters rendered when Leads tab is active:

| Filter | Type |
|---|---|
| Date range (on `CreatedOn`) | from / to date inputs |
| Agent | multi-select with pills |
| Stage | multi-select checkboxes |
| MQL score | Segmented: Any / ≥ 3 / = 5 (MQL only) |
| Condition | multi-select |
| City | text input (substring match) |

### Backend route: `GET /api/inside-sales/leads`

Query params: `date_from`, `date_to`, `page`, `page_size`, `agents` (comma-sep), `stage` (comma-sep), `mql_min` (int), `condition` (comma-sep), `city` (substring).

Logic:
1. Call `Leads.Get` with `CreatedOn >=` and `CreatedOn <=` filter; request only the field list from Section 2
2. Apply server-side filters (agents, stage, city, condition substring)
3. Compute `mql_score` and `mql_signals` per lead via `compute_mql_score()`
4. Compute `total_dials`, `connect_rate`, `frt_seconds` (proxy), `lead_age_days`, `days_since_last_contact`
5. Return `LeadListResponse` (no DB query — no eval join in listing)

---

## 5. Lead Drilldown

Route: `/inside-sales/leads/:prospectId`
Route constant name: `INSIDE_SALES_LEAD_DETAIL` → `/inside-sales/leads/:prospectId`
Back button: "Back to Leads"

### Page header

```
← Back to Leads

[Lead Name]  [Stage badge]  [MQL badge ●●●●●]               [Evaluate ▾]
+91-98765...  ·  Hyderabad  ·  Diabetes
```

**Evaluate button logic:**
- Enabled when: `call_history` contains at least one call where `recording_url` is non-null AND `eval_score` is null (i.e., has a recording and has never been evaluated).
- Disabled + tooltip "No unevaluated recordings" otherwise.
- Opens eval wizard pre-loaded with the most recent call meeting the above criteria.

### Profile card (two columns)

**Left — Contact & Source:**
Phone (mono), Email, City, Age Group, Source + SourceCampaign, Assigned Agent, Lead Created (formatted date).

**Right — Health Profile:**
Condition, HbA1c, Blood sugar band, Diabetes duration, Current management, Goal, Intent to pay, Preferred call time.

All null fields render as label + `—`. No field is hidden.

### KPI strip (5 tiles)

Tiles 1–4 are always shown. Tile 5 is conditional:

```
┌────────────┐ ┌──────────┐ ┌────────────┐ ┌────────────────┐ ┌──────────────────────┐
│ FRT (exact)│ │ Total    │ │ Connect    │ │ Counseling     │ │ Tile 5 (conditional) │
│ 2h 15m  🔴 │ │ Dials 17 │ │ Rate  43%  │ │ Sessions  2    │ │  see below           │
│ (SLA: 1h)  │ │          │ │            │ │ (calls ≥10min) │ │                      │
└────────────┘ └──────────┘ └────────────┘ └────────────────┘ └──────────────────────┘
```

**Tile 5:**
- If `mx_Preferred_Time_for_Call_with_Health_Counsellor` is non-null: **Callback Adherence** tile showing `adherence_delta` (e.g. "45m after preferred time"). `—` if `adherence_delta_seconds` is None.
- Otherwise: **Lead Age** tile showing `lead_age_days` in days.

FRT tile uses exact value from call history (Section 3.4 drilldown formula). If call history is flagged as incomplete (see Section 2), FRT tile shows `—` with tooltip "History incomplete".

### Tab bar

```
[ Call Timeline ]  [ Evaluations ]
```

### Call Timeline tab

Full-width table, same style as existing tables. Columns:

| Column | Display |
|---|---|
| Timestamp | Formatted datetime, descending |
| Agent | Name. `—` if null |
| Duration | `mm:ss`. Green + bold if `duration_seconds ≥ 600`. `—` if 0 and status is not Answered |
| Status | Badge: "Answered" green / "Not Answered" muted-red / "Call Failure" gray |
| Eval score | `scoreColor`-coded score chip if `eval_score` non-null. `—` otherwise |
| Actions | `▶` play icon if `recording_url` non-null; navigates to `InsideSalesCallDetail` for that call |

The call row corresponding to the eval shown in the Evaluations tab carries a left-border accent.

**Zero state (no calls, no error):** `EmptyState` — "No call activity found", "No calls were recorded for this lead in LeadSquared."

**Error state (LSQ fetch failed):** `EmptyState` with `AlertTriangle` icon (red) — "Failed to load call history", "Could not connect to LeadSquared. Try refreshing." + Retry button. Displayed separately from the zero-call state.

**Incomplete history warning** (when `history_truncated = true`): amber inline banner above the table — "Showing the first 200 calls — call history may be incomplete. Metrics marked ⚠ may be inaccurate."

### Evaluations tab

Renders `<CallResultPanel thread={latestEvalThread} />` — the component from UX improvements Item 1. No re-implementation.

Run selector above panel when multiple evals exist:
```
[←]  Evaluation 2 of 3  ·  Mar 22, 11:04 AM  [→]
```

Zero state: `EmptyState` — icon `FileText`, title "Not yet evaluated", description "Select a call from the timeline and click Evaluate.", CTA "Evaluate".

### Backend route: `GET /api/inside-sales/leads/{prospect_id}/detail`

Logic:
1. Fetch full lead record via `Leads.GetById`
2. Fetch call history: paginate `RetrieveByActivityEvent` (event codes `[21, 22]`, date range `[CreatedOn, now]`, `PageSize=500`); filter server-side by `RelatedProspectId == prospect_id`; cap at 200 matching records; set `history_truncated=True` if more exist
3. Compute exact FRT (Section 3.4), counseling count/rate (Section 3.5), callback adherence (Section 3.6)
4. Compute MQL score + signals (Section 3.2)
5. Fetch all `ThreadEvaluation` records where `thread_id IN [c.activity_id for c in call_history]` and `EvalRun.app_id == "inside-sales"` and `EvalRun.tenant_id == auth.tenant_id` and `EvalRun.user_id == auth.user_id` — ordered by `created_at desc`. Join `eval_score` back onto each `LeadCallRecord` where applicable. When multiple `ThreadEvaluation` records share the same `thread_id` (call re-evaluated), use the one with the latest `created_at` as the `eval_score` on that `LeadCallRecord`.
6. Return `LeadDetailFullResponse`

---

## 6. New Backend Schemas

```python
class LeadListRecord(CamelModel):
    prospect_id: str
    first_name: str
    last_name: Optional[str]
    phone: str
    prospect_stage: str
    city: Optional[str]
    age_group: Optional[str]
    condition: Optional[str]
    hba1c_band: Optional[str]
    intent_to_pay: Optional[str]
    agent_name: Optional[str]
    rnr_count: int                      # 0 when mx_RNR_Count is null
    answered_count: int                 # 0 when mx_Answered_Call_Count is null
    total_dials: int                    # rnr_count + answered_count
    connect_rate: Optional[float]       # None when total_dials == 0
    frt_seconds: Optional[int]          # None when null or negative (proxy)
    lead_age_days: int
    days_since_last_contact: Optional[int]  # None when ProspectActivityDate_Max is null
    mql_score: int                      # 0–5
    mql_signals: dict[str, bool]        # keys: age, city, condition, hba1c, intent
    created_on: str
    last_activity_on: Optional[str]
    source: Optional[str]
    source_campaign: Optional[str]

class LeadListResponse(CamelModel):
    leads: list[LeadListRecord]
    total: int
    page: int
    page_size: int

class LeadCallRecord(CamelModel):
    activity_id: str
    call_time: str
    agent_name: Optional[str]           # nullable: system-logged calls may lack agent
    duration_seconds: int
    status: str                         # Answered / NotAnswered / CallFailure
    recording_url: Optional[str]        # nullable: not all answered calls are recorded
    eval_score: Optional[float]
    is_counseling: bool                 # duration_seconds >= 600

class LeadDetailFullResponse(CamelModel):
    # Profile
    prospect_id: str
    first_name: str
    last_name: Optional[str]
    phone: str
    email: Optional[str]
    prospect_stage: str
    city: Optional[str]
    age_group: Optional[str]
    condition: Optional[str]
    hba1c_band: Optional[str]
    blood_sugar_band: Optional[str]
    diabetes_duration: Optional[str]
    current_management: Optional[str]
    goal: Optional[str]
    intent_to_pay: Optional[str]
    job_title: Optional[str]
    preferred_call_time: Optional[str]
    agent_name: Optional[str]
    source: Optional[str]
    source_campaign: Optional[str]
    created_on: str
    # MQL
    mql_score: int
    mql_signals: dict[str, bool]
    # Computed metrics (all Optional — None renders as —)
    frt_seconds: Optional[int]          # exact from call history; None if negative or missing
    total_dials: int
    connect_rate: Optional[float]       # None when total_dials == 0
    counseling_count: int
    counseling_rate: Optional[float]    # None when answered count (from history) == 0
    callback_adherence_seconds: Optional[int]  # None when preferred_call_time null or no call after it
    lead_age_days: int
    days_since_last_contact: Optional[int]
    # Call history
    call_history: list[LeadCallRecord]
    history_truncated: bool             # True when LSQ returned > 200 matching records
    # Eval history (ThreadEvalRow — existing type, reused)
    eval_history: list
```

---

## 7. Component Map

### New files

| File | Purpose |
|---|---|
| `backend/app/services/lsq_client.py` | Add `fetch_leads()`, `fetch_lead_activities_for_prospect()`, `compute_mql_score()` |
| `backend/app/schemas/inside_sales.py` | Add `LeadListRecord`, `LeadListResponse`, `LeadCallRecord`, `LeadDetailFullResponse` |
| `backend/app/routes/inside_sales.py` | Add `GET /leads` and `GET /leads/{prospect_id}/detail` |
| `src/features/insideSales/pages/InsideSalesLeadDetail.tsx` | Lead drilldown page |
| `src/features/insideSales/components/MqlScoreBadge.tsx` | Score + 5 signal dots + hover tooltip |
| `src/features/insideSales/components/LeadCallTimeline.tsx` | Call history table (Call Timeline tab content) |
| `src/services/api/insideSales.ts` | Add `fetchLeads()`, `fetchLeadDetail()` |

### Modified files

| File | Change |
|---|---|
| `src/features/insideSales/pages/InsideSalesListing.tsx` | Leads tab at index 0, All Calls at index 1; wire leads tab content |
| `src/features/insideSales/components/CallFilterPanel.tsx` | Leads-specific filters rendered conditionally based on active tab |
| `src/stores/insideSalesStore.ts` | Add `leads`, `leadsTotal`, `leadsPage`, `leadsFilters`, `leadsLoading` slice |
| `src/config/routes.ts` | Add `INSIDE_SALES_LEAD_DETAIL = '/inside-sales/leads/:prospectId'` |

### Reused without modification

| Component | Used where |
|---|---|
| `CallResultPanel` | Evaluations tab in drilldown |
| `EmptyState` | All zero/error states |
| `scoreColor` / `getScoreBand` from `scoreUtils` | Eval score chips in timeline |
| Existing eval wizard | Evaluate button in drilldown header |

---

## 8. Invariants

- **Internal DB queries** (ThreadEvaluation joins) filter by `tenant_id` + `user_id` from `AuthContext` without exception. LSQ API calls are scoped by API key — they are not per-tenant filtered at the network level.
- `compute_mql_score()` is a pure function: no side effects, no DB calls, no external calls. Input: lead field dict. Output: `(int, dict[str, bool])`.
- `fetch_lead_activities_for_prospect()` filters `RelatedProspectId` server-side before returning — never returns unfiltered activity data to routes or frontend.
- `connect_rate` is `None` when `total_dials == 0`. Never divide by zero.
- `counseling_rate` is `None` when `total_answered_from_history == 0`. Never divide by zero.
- `callback_adherence_seconds` is `None` when preferred call time is null or when no call exists after that time.
- `frt_seconds` is `None` when the computed delta is negative. Negative FRT indicates LSQ data quality issues (clock skew, import artefacts) and must not be displayed.
- `days_since_last_contact` is `None` (not 0) when `ProspectActivityDate_Max` is null — absence of activity is distinct from same-day activity.
- MQL score treats null/blank field values as signal not met (0). Signals are never inferred from adjacent fields.
- `history_truncated = True` suppresses FRT, counseling count, and counseling rate display with a ⚠ indicator — incomplete history must not produce silently wrong metrics.
- `recording_url` in `LeadCallRecord` is `Optional[str]` — the play button is only rendered when non-null.
- `agent_name` in `LeadCallRecord` is `Optional[str]` — system-initiated calls may have no agent.
