# Call Quality Evals — Inside Sales Agent Performance Platform

## Goal

Evaluate inside sales agent call performance using LLM judges. Agents make calls via LeadSquared (Ozonetel telephony integration). Call recordings (MP3) are stored on Ozonetel's S3. This app ingests call data from LSQ APIs, displays recordings in a searchable listing, and runs rubric-based LLM evaluations on transcripts.

**Target users:** Sales ops, QA leads, team managers — reviewing human agent performance, not AI output.

---

## Data Source: LeadSquared API

### Credentials

| Key | Value |
|-----|-------|
| API Base URL | `https://api-in21.leadsquared.com/v2/` |
| Access Key | `u$r6ec1c6a13b7d4d8d9448d9042a153d9d` |
| Secret Key | `4617b1110e6058e1f9311f79fb9005b23842aa81` |

Auth is passed as query params: `?accessKey=...&secretKey=...`

### API Endpoints Used

#### 1. Get Activity Types (discovery)

```
GET /v2/ProspectActivity.svc/ActivityTypes.Get?accessKey=...&secretKey=...
```

Returns all activity types with event codes. Used once to discover phone call event codes.

#### 2. Retrieve Phone Call Activities (primary ingestion)

```
POST /v2/ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent?accessKey=...&secretKey=...
```

Request body:
```json
{
  "Parameter": {
    "FromDate": "2026-03-24 00:00:00",
    "ToDate": "2026-03-24 23:59:59",
    "ActivityEvent": 22
  },
  "Paging": {
    "PageIndex": 1,
    "PageSize": 100
  },
  "Sorting": {
    "ColumnName": "CreatedOn",
    "Direction": 1
  }
}
```

**Rate limit:** 25 API calls per 5 seconds. Pagination required (max 100/page).

#### 3. Get Lead Details (hydrate lead name/phone)

```
GET /v2/Leads.svc/Leads.GetById?accessKey=...&secretKey=...&id={ProspectId}
```

Or bulk:
```
GET /v2/Leads.svc/Leads.GetByIds?accessKey=...&secretKey=...
```

Needed because call activities only return `RelatedProspectId`, not lead name.

---

## Event Code Mapping

Phone call activity types in this LSQ account:

| Event Code | Type | Activity Name |
|-----------|------|---------------|
| **21** | 3 (System - Telephony) | Phone Call - Inbound |
| **22** | 3 (System - Telephony) | Phone Call - Outbound |
| 103 | 2 (Custom) | Phone Conversation |
| 204 | 2 (Custom) | Welcome Call |
| 205 | 2 (Custom) | In Active Patient Call |
| 206 | 2 (Custom) | Doctor Consultation Booking Call |
| 207 | 2 (Custom) | Device, Lab Tests, Tickets related and other calls |
| 208 | 2 (Custom) | Assessment Call - Diet Plan |
| 211 | 2 (Custom) | Followup Call - Diet Plan |
| 213 | 2 (Custom) | Assessment Call - Physio |
| 226 | 2 (Custom) | Weekly Follow up call - RM |
| 236 | 2 (Custom) | Introductory Call - Pre MB score |
| 237 | 2 (Custom) | Ringing No Response |
| 238 | 2 (Custom) | Follow up or Call Back |
| 241 | 2 (Custom) | Phone Conversation New |

**Primary targets for ingestion:** Event codes **21** (inbound) and **22** (outbound) — these are the system telephony activities logged by Ozonetel webhook.

Full activity type list: 90 types total (email, web, custom, sales, privacy, etc.).

---

## Call Activity Field Mapping

Each phone call activity (event 21/22) returns these fields:

### Standard Fields

| Field | Description | Example |
|-------|-------------|---------|
| `ProspectActivityId` | Activity UUID | `91ce9156-2761-11f1-b68e-0a65ee4efb23` |
| `RelatedProspectId` | Lead UUID (needs hydration for name) | `5556cdeb-f2b6-433a-b5de-6f4f695b365a` |
| `ActivityEvent` | Event code (21 or 22) | `22` |
| `Status` | Call outcome | `Answered` / `NotAnswered` |
| `CreatedOn` | Timestamp (UTC) | `2026-03-24 09:09:52` |
| `CreatedByName` | Agent display name | `B Himani` |
| `CreatedByEmailAddress` | Agent email | `b.himani@tatvacare.in` |
| `ModifiedOn` | Last update timestamp | `2026-03-24 09:12:23` |

### Custom Fields (mx_Custom_N)

| Field | Maps To | Example |
|-------|---------|---------|
| `mx_Custom_1` | Display number (caller ID) | `917971406375` |
| `mx_Custom_2` | Call start time | `2026-03-24 09:09:52` |
| `mx_Custom_3` | Duration (seconds) | `74` |
| `mx_Custom_4` | **Recording URL (S3 MP3)** | `https://s3-ap-south-1.amazonaws.com/3m-pu.ozonetel.com/digicare_health/DIA...mp3` |
| `mx_Custom_5` | Source | `Web` |
| `mx_Custom_6` | Connector ID | `eb749046-4ae1-429c-9c36-93c93f3de449` |
| `mx_Custom_7` | Call status label | `Answered` |

### ActivityEvent_Note (delimited string)

Contains all Ozonetel data in `Key{=}Value{next}` format, including the full `SourceData` JSON:

```json
{
  "SourceNumber": "514375",
  "DestinationNumber": "9112299667",
  "DisplayNumber": "917971406375",
  "StartTime": "2026-03-24 14:39:52",
  "EndTime": "2026-03-24 14:41:15",
  "CallDuration": 74,
  "Status": "Answered",
  "CallNotes": "call back",
  "CallerSource": "call back",
  "ResourceURL": "https://s3-ap-south-1.amazonaws.com/3m-pu.ozonetel.com/digicare_health/DIA...mp3",
  "Direction": "Outbound",
  "CallSessionId": "17692177434339291",
  "AgentName": "b.himani@tatvacare.in",
  "Notes": ""
}
```

**Key:** `mx_Custom_4` is the clean, direct recording URL. Unanswered calls have empty `mx_Custom_4` and `ResourceURL`.

---

## Ozonetel Webhook Reference (DO NOT CALL)

This webhook is called by Ozonetel on call completion. Documented here for context only.

```
POST http://telephony-in21.leadsquared.com/1/api/Telephony/LogCallComplete/ORG76235/24e4658df811521a871be13e2ba748ad1a/eb749046-4ae1-429c-9c36-93c93f3de449
```

This is what creates the phone call activity in LSQ. We read the result, never invoke the webhook.

---

## Volume & Scale

- ~683 outbound calls per day (observed on 2026-03-24)
- Inbound volume TBD (need to query event code 21)
- LSQ API rate limit: 25 calls / 5 seconds
- At 100 records/page, ~7 API calls to fetch a full day of outbound calls

---

## Ingestion Strategy

### Approach: On-demand sync with caching

1. User triggers "Sync Calls" for a date range
2. Backend paginates through LSQ API (event codes 21 + 22)
3. Upserts call records into local DB (keyed by `ProspectActivityId`)
4. Hydrates lead names via bulk lead lookup (batch `RelatedProspectId`s)
5. Stores metadata + recording URL; does NOT download MP3s at sync time

### Open Questions

| Question | Impact | How to verify |
|----------|--------|---------------|
| Do S3 recording URLs expire? | If yes, must mirror MP3s to own storage on sync | Try downloading a week-old URL |
| Lead bulk lookup limits? | Affects hydration strategy | Test `GetByIds` with 100 IDs |
| Are custom event codes (204-241) also Ozonetel calls? | May need to ingest beyond 21/22 | Check if those have `mx_Custom_4` populated |

---

## UI/UX: Listing Page

### Table Columns

| Column | Source | Sortable | Filterable |
|--------|--------|----------|------------|
| Date/Time | `mx_Custom_2` | Yes | Date range picker |
| Agent | `CreatedByName` | Yes | Dropdown (agent list) |
| Lead Name | Hydrated from `RelatedProspectId` | Yes | Search |
| Duration | `mx_Custom_3` (formatted mm:ss) | Yes | Range slider |
| Direction | Event code 21=Inbound, 22=Outbound | — | Toggle |
| Call Status | `Status` | — | Dropdown |
| Eval Status | From eval_runs table | — | Dropdown (Not Evaluated / Evaluated / In Progress) |
| Score | Overall eval score (post-eval) | Yes | Range |
| Actions | Play / Download / Evaluate buttons | — | — |

### Filters

- **Agent** — dropdown, multi-select from synced agent list
- **Date range** — date picker (default: today)
- **Call status** — Answered / NotAnswered / All
- **Direction** — Inbound / Outbound / All
- **Duration** — min/max range (skip <10s drops)
- **Eval status** — Not Evaluated / Evaluated / In Progress
- **Score range** — 0-100 slider (only for evaluated calls)
- **Search** — free text (lead name, agent name, phone number)

### Pagination

- Server-side pagination (calls can be high volume)
- 25 items per page default
- Total count displayed

### Inline Audio Playback

- Reuse existing wavesurfer.js player (`SegmentAudioPlayer` pattern)
- Click play on any row → mini player loads S3 MP3 URL
- If transcript exists, show synced transcript alongside audio

### Download

- Single call: download MP3 directly from S3 URL
- Bulk: select multiple → zip download (or sequential, depending on volume)

---

## UI/UX: Single Call Detail Page

- Full audio player (wavesurfer.js, waveform visualization)
- Transcript panel (if transcribed) — clickable words jump to audio position
- Call metadata card (agent, lead, duration, time, direction, status)
- Evaluation panel:
  - If not evaluated: "Evaluate" button → triggers single eval
  - If evaluated: scorecard with per-dimension scores + evidence excerpts
- Notes / manual annotation field

---

## Evaluation Flow

### Difference from existing evals

| Aspect | Existing (Voice Rx / Kaira) | Call Quality Evals |
|--------|----------------------------|-------------------|
| Evaluates | AI agent output | Human agent performance |
| Input | Audio/transcript or chat thread | Sales call transcript |
| Criteria | Intent accuracy, rule compliance, efficiency | Rubric: discovery questions, objection handling, script adherence, empathy, closing |
| Scoring | Binary verdicts (correct/incorrect) + categorical | 1-5 scale per dimension + weighted overall score |
| Evidence | Rule violations cited | Transcript excerpts cited as evidence |

### Evaluation Pipeline

```
Call Record (from LSQ sync)
  → Transcription (Gemini, if not already transcribed)
  → LLM Judge (rubric-based scoring on transcript)
  → Per-dimension scores + evidence + overall score
  → Stored as EvalRun + ThreadEvaluation
```

### Single Call Evaluation

1. User clicks "Evaluate" on a call
2. System checks if transcript exists; if not, transcribes first
3. User selects evaluation rubric (or uses default)
4. Job created → background worker runs LLM judge
5. Results displayed inline on call detail page

### Bulk Evaluation (Step Wizard)

```
Step 1: SELECT CALLS
  - Filter by date range, agent, status, duration
  - Checkbox selection (select all / individual)
  - Show count: "247 calls selected"

Step 2: CHOOSE RUBRIC
  - Pick evaluation criteria template
  - Toggle individual dimensions on/off
  - Set dimension weights (if custom)

Step 3: CONFIGURE LLM
  - Model selection (Gemini, GPT-4, Claude)
  - Temperature
  - Transcription model (if calls need transcription)

Step 4: REVIEW & LAUNCH
  - Summary: N calls, M need transcription, estimated cost
  - "Start Evaluation" → creates Job
  - Progress bar (reuse existing job tracker UI)
```

### Rubric Design (starter template)

| Dimension | Weight | Scoring | What LLM Judge Checks |
|-----------|--------|---------|----------------------|
| Opening & Introduction | 10% | 1-5 | Did agent introduce themselves and state purpose? |
| Discovery Questions | 25% | 1-5 | Did agent ask about patient condition, needs, timeline? |
| Program Explanation | 20% | 1-5 | Did agent clearly explain the PSP offering? |
| Objection Handling | 15% | 1-5 | How well did agent address concerns/pushback? |
| Empathy & Tone | 15% | 1-5 | Was agent empathetic, patient, professional? |
| Closing & Next Steps | 15% | 1-5 | Did agent set clear next steps, follow-up, or enrollment? |

Weights and dimensions should be configurable per campaign/program. This maps to the existing `Evaluator` model with custom schemas.

---

## Reports & Analytics

### Per-Agent Dashboard

- Overall score trend (line chart over weeks)
- Per-dimension radar chart (strengths/weaknesses)
- Call volume and answer rate
- Worst calls (lowest scores) — direct links for coaching review
- Improvement tracking (score delta week-over-week)

### Team Dashboard

- Agent leaderboard (ranked by overall score)
- Team average by dimension (bar chart)
- Common failure patterns across team ("60% of agents skip discovery questions")
- Volume metrics (calls/day, avg duration, answer rate)

### Run Reports (per eval batch)

Reuse existing `EvaluationAnalytics` + `cross_run_aggregator` pattern:
- Health score (weighted grade across rubric dimensions)
- Verdict distribution per dimension
- Exemplars (best call, worst call, most improved)
- Narrative summary (LLM-generated coaching insights)
- PDF export

---

## Platform Mapping: What to Reuse vs. Build New

### Reuse directly

| Component | Location | Adaptation needed |
|-----------|----------|-------------------|
| Background job worker | `backend/app/services/job_worker.py` | Register new job handler |
| wavesurfer.js audio player | `src/features/transcript/` | Minimal — same MP3 playback |
| EvalRun + ThreadEvaluation models | `backend/app/models/` | Add `app_id = "call-quality"` |
| Job progress polling UI | `src/stores/jobTrackerStore` | None |
| Cross-run analytics + reports | `backend/app/services/reports/` | New aggregator for rubric scores |
| PDF export pipeline | `backend/app/services/reports/pdf_template.py` | New template for call eval report |
| Custom evaluator framework | `backend/app/services/evaluators/` | New evaluator for rubric scoring |
| Auth + multi-tenancy | `backend/app/auth/` | None |
| LLM factory (Gemini/OpenAI/Claude) | `backend/app/services/evaluators/llm_base.py` | None |
| Zustand stores pattern | `src/stores/` | New store for call records |

### Build new

| Component | Description |
|-----------|-------------|
| LSQ API client | Service to fetch call activities, paginate, rate-limit |
| Call record model | DB model for synced call data (metadata + recording URL + transcript) |
| Ingestion route | `POST /api/calls/sync` — trigger LSQ sync for date range |
| Calls listing route | `GET /api/calls` — paginated, filtered, searchable |
| Calls listing page | Table with filters, inline player, eval status |
| Call detail page | Full player + transcript + eval scorecard |
| Rubric evaluator | LLM judge prompt for human agent scoring |
| Bulk eval wizard | 4-step wizard UI for batch evaluation |
| Agent performance dashboard | Per-agent and team-level analytics views |
| Transcription trigger | On-demand or bulk transcription of call recordings |

---

## Risks & Open Items

1. **S3 URL durability** — Verify if Ozonetel S3 URLs expire. Test with a week-old recording URL. If they expire, must mirror MP3s to own storage on ingestion.

2. **Transcription cost** — ~683 calls/day. At ~1 min avg, that's ~11 hours of audio/day. Gemini transcription pricing applies. Consider: only transcribe calls selected for evaluation, not all synced calls.

3. **Lead name hydration** — Each call only has `RelatedProspectId`. Need to batch-fetch lead names. Test bulk lead API limits.

4. **Rubric design** — Technical platform is the easy part. The rubric (what makes a "good call") needs input from sales ops / QA team. Start with 3-5 concrete dimensions before building.

5. **Rate limiting** — LSQ allows 25 API calls / 5 seconds. For bulk sync of historical data (e.g., 30 days × 683 calls/day), need throttled pagination. ~205 API calls for 30 days of outbound data.

6. **Custom event codes** — Event codes 204-241 are custom call types (Welcome Call, Assessment Call, etc.). These may also have recordings in `mx_Custom_4`. Decide if these should be ingested alongside system telephony events (21/22).

7. **Hindi/regional language transcription** — Inside sales calls in India are likely in Hindi or mixed Hindi-English. Verify Gemini transcription quality for these languages. May need Whisper or specialized model.
