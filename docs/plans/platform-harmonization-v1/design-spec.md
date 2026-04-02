# Platform Harmonization — Design Spec v1

**Date:** 2026-04-02
**Status:** Approved direction, pending implementation planning
**Scope:** Evaluator UI unification, asset ownership model, app config schema, RBAC integration

---

## 1. Problem Statement

The platform has three apps (Voice Rx, Kaira Bot, Inside Sales) that evolved independently. Each has its own evaluator UI patterns, wizard flows, and hardcoded branches. Assets are mostly user-scoped with no consistent sharing model, meaning team members operate in isolation and cannot easily discover or reuse each other's evaluators, prompts, schemas, or app contracts. App identity is scattered across code as string checks (`if appId === "inside-sales"`), making it impossible to onboard a new app without code changes.

The platform is pre-launch. No production data to preserve. Clean structural changes are preferred over backward-compatible migrations.

### 1.1 Design Guardrails From Current Codebase

This spec is constrained by existing backend and frontend behavior that must either be preserved or updated atomically:

- **LLM settings remain private in v1.** Current runtime credential lookup resolves `llm-settings` by `(tenant_id, user_id, app_id="")` and the repo invariant explicitly requires per-user-per-tenant storage. This rules out shared API keys in this phase.
- **Variable picking is already hybrid.** `VariablePickerPopover` currently loads app-level variables from the evaluator variable registry and, for Voice Rx API listings, merges in listing-specific API response paths. Harmonization must preserve that split instead of forcing all variables into static app config.
- **Prompts and schemas already behave like immutable version rows.** Settings UIs save edits as new versions rather than mutating built-ins in place. Sharing must preserve this versioned library model.
- **`displayMode` is still consumed outside the evaluator editor.** Report aggregation, eval-run output rendering, exports, and seed data still depend on `displayMode`. Removing it requires an explicit output-schema cutover plan, not just a wizard refactor.
- **System defaults already use the system tenant.** Current readers load seeded defaults through `SYSTEM_TENANT_ID` / `SYSTEM_USER_ID`. Harmonization should preserve that access pattern instead of introducing a second competing "tenant-visible" system model.
- **Long-running LLM assistance already belongs to the job model.** The repo architecture requires multi-second operations to run through jobs and `submitAndPollJob()`, not bespoke component polling or ad hoc synchronous loops.

### 1.2 Traceability Rule For This Spec

Every structural decision in this document names:

- **Upstream impact:** current models, routes, stores, or invariants that force the design.
- **Downstream impact:** which API shapes, UI components, stores, reports, or runtime flows must change because of the decision.

If an item cannot be traced both directions, it is not considered designed.

---

## 2. Design Decisions Made

### 2.1 Evaluator Display: Cards → Table

**Decision:** Replace all evaluator card grids with a unified table across all three apps.

**Table columns:** Name | Visibility | Owner | Main Metric | Output Fields (as tags) | Model | Actions (⋮)

- Click any row to expand and see full field details (types, thresholds, roles)
- Pagination for all apps, consistent behavior
- ⋮ menu actions: Edit, Duplicate, Share, Make Private, Fork, Delete — shown/hidden based on ownership and RBAC
- Filter tabs: All | Shared | Mine (replaces the old Registry/All split)
- One shared component: `EvaluatorsTable`. No app-specific table variants.

### 2.2 Evaluator Wizard: Unified Create/Edit Flow

**Decision:** One `CreateEvaluatorWizard` component for all apps. App-specific capabilities are plugged in via app config, not code branches.

**Steps:**

1. **Prompt** — Name + Model (compact row) + prompt textarea with variable picker. Includes a build mode toggle: "Write Prompt" (default) vs "Use Rubric" (only shown if `appConfig.features.hasRubricMode` is true). Rubric mode shows the existing RubricBuilder which auto-generates both prompt and schema.
2. **Schema** — Output fields table. If coming from "Write Prompt" mode, the wizard runs the draft-generation job before showing this step. If coming from "Use Rubric" mode, fields are pre-populated from the rubric. Either way, the same schema table component renders and the user can edit.
3. **Rules** — Only shown if `appConfig.features.hasRules` is true. The draft-generation job suggests rule matches from the app's published catalog. User can add/remove via a rule picker secondary overlay. If this step doesn't exist, the Schema step footer shows "Save Evaluator."

**Build mode toggle behavior:**
- "Write Prompt" → user writes prompt → on Next, draft-generation job runs → schema table shown
- "Use Rubric" → user builds rubric (dimensions, checks, compliance gates, thresholds) → RubricBuilder auto-generates prompt + schema → schema table shown pre-filled

Both paths converge on the same schema table. The schema table is the single source of truth for output field definitions.

### 2.3 Schema Table: Simplified Display Model

**Decision:** The old `displayMode` (header/card/hidden) column is removed. Role determines visibility.

**Roles:**
- `metric` — Visible in table row (expanded) and eligible to be pinned as main metric (★). Thresholds shown for number types.
- `detail` — Visible in expanded row only. Boolean gates, sub-scores, flags.
- `reasoning` — Hidden from UI entirely. Internal audit trail. Row visually dimmed in the schema builder.

**Main metric (★):** A star icon on each row. Only one can be active per evaluator. Only clickable on `metric` role fields. The pinned field's value shows in the Main Metric column of the evaluators table.

### 2.4 Draft from Prompt: Job-Backed LLM Assistance

**Decision:** When the user moves from Prompt → Schema, the wizard starts a background job that generates an evaluator draft from the prompt. This job is the single LLM-assisted step for both schema extraction and rule auto-match.

**Job:** `generate-evaluator-draft`
- Submitted through `submitAndPollJob()`, not custom component polling
- Input: `{ prompt: string, appId: string, sourceType?: string, listingId?: string }`
- Output:
  - `outputFields: EvaluatorOutputField[]`
  - `matchedRuleIds: string[]`
  - `warnings: string[]`
- Uses the current user's private `llm-settings` from `(tenant_id, user_id, app_id="")`
- If credentials are missing or invalid, the job returns a stable error and the wizard falls back to manual schema/rule setup without blocking save

**Behavior:**
- Runs automatically on transition from Prompt → Schema
- Shows a loading state: "Generating evaluator draft from prompt..."
- User can click "Skip — build manually" to bypass draft generation entirely
- After completion, a banner shows: "Generated N output fields from prompt — review and adjust below"
- "Re-generate" is available if the user edits the prompt and wants fresh suggestions
- The job infers patterns like "Rate 1-5" → number + metric + thresholds, "yes/no" → boolean + detail, "reasoning/explanation" → text + reasoning

**Why this shape:**
- Upstream: repo architecture requires multi-second LLM operations to use the job system
- Downstream: the wizard gets one deterministic draft payload instead of stitching together separate extraction and rule-matching calls

### 2.5 Rule Picker: Generic, Prop-Driven

**Decision:** The rule picker is a generic component that receives rules as data, not an app-specific feature.

**Component:** `<RulePicker rules={appRules} selected={linkedRuleIds} onChange={setLinkedRuleIds} />`

- Opens as a secondary overlay on top of the primary wizard overlay
- Shows all rules from the app's catalog with search and tags
- Pre-checks auto-matched rules from the draft-generation job
- Auto-matched rules show an "auto" badge, user can remove them
- Rules are stored as references (IDs) on the evaluator, not copies. Rule updates in the catalog propagate to all evaluators using them.
- Rules are injected into the evaluation prompt at runtime as a "Rules to verify" section.

**Rule catalog contract:**
- The full published rule catalog does **not** live inside `apps.config`
- `apps.config` only declares rule capability and catalog metadata
- The runtime catalog is fetched from a dedicated backend rules API
- In v1, the published catalog is persisted as an app-scoped shareable setting row (`key='rule-catalog'`) so source systems can update rules without frontend or backend code changes

**Enabling rules for any app:** Set `appConfig.features.hasRules = true` and expose a published rule catalog for that app. No code changes. The wizard step auto-appears, the picker auto-populates.

### 2.6 Variable Picker: Hybrid Static + Dynamic Sources

**Decision:** The variable picker becomes app-config directed, not app-config only.

**Static variables:** `appConfig.evaluator.variables`
- App-wide variables that are always available for the app
- Examples: `chat_transcript`, `session_metadata`, `agent_name`

**Dynamic variables:** existing backend sources, enabled by app config
- Evaluator variable registry (`GET /api/evaluators/variables`) for runtime-aware variables by app and source type
- Listing API response paths (`GET /api/evaluators/variables/api-paths`) for Voice Rx API listings

**Config contract:**
- App config defines the static variable catalog
- App config also declares which dynamic sources are enabled for the app
- `VariablePickerPopover` merges static config variables with enabled dynamic sources into one grouped list

**Why this model:**
- Upstream: Voice Rx already needs listing-specific API paths, which cannot be represented statically
- Downstream: shared prompt UI can stop hardcoding app branches while preserving listing-aware variables where required

- Opens as a secondary overlay
- Variables grouped by category
- Clicking "Insert" places `{{variable}}` at cursor position in prompt textarea
- Same component for all apps, data differs based on app config and runtime context

### 2.7 Frontend Architecture Rules

- All colors, spacing, typography from the existing design token system and component library. No hardcoded hex values, no inline styles for theming.
- All new components are generic and importable. No app-specific component files for shared patterns.
- `cn()` for all conditional class merging (Tailwind v4 JIT requirement).
- No `if (appId === "x")` in shared components. Feature checks go through `appConfig.features.*`.
- App display names read from `appConfig.displayName`, never hardcoded strings.
- Any net-new UI primitive (e.g., `VisibilityBadge`, `StarToggle`) is added to `src/components/ui/` as a generic component.

### 2.8 Output Schema v2 Cutover

**Decision:** `output_schema` moves to a v2 model centered on `role` + `isMainMetric`, and the cutover is atomic.

**v2 field semantics:**
- `role: 'metric' | 'detail' | 'reasoning'`
- `isMainMetric: boolean` on exactly one `metric` field
- `thresholds` remain only on numeric fields
- `displayMode` is removed from persisted evaluator definitions once all readers are updated

**Atomic cutover is required because the following consumers still read `displayMode`:**
- custom evaluation report aggregation
- eval-run output renderers
- CSV/export helpers
- seeded evaluator payloads
- evaluator editor and preview UIs

**Cutover rule:**
- Writers do not switch to v2 until all known readers have been updated to the new visibility rules
- Because the platform is pre-launch, we prefer an all-at-once code cutover plus reseeding over a long compatibility window

**Downstream reader behavior in v2:**
- Visible fields = `metric` and `detail`
- Hidden fields = `reasoning`
- Main metric = `isMainMetric === true`
- Report aggregation operates on visible fields and uses `isMainMetric` to find the primary metric

---

## 3. Asset Ownership Model

### 3.1 Core Concept

Every entity in the system is an asset with an ownership and visibility property. Ownership is always a user. Visibility determines who else can see and interact with the asset.

### 3.2 ShareableMixin

A new SQLAlchemy mixin applied to entities that support sharing. Added alongside the existing `TenantUserMixin` and `TimestampMixin`.

**Columns:**

| Column | Type | Default | Purpose |
|---|---|---|---|
| `visibility` | `enum('private', 'app')` | `'private'` | Who can see this asset inside a tenant |
| `forked_from` | `same type as entity PK, FK to same table, nullable` | `null` | Lineage — which asset was this copied from |
| `shared_by` | `uuid, FK to users, nullable` | `null` | Who changed visibility (audit) |
| `shared_at` | `timestamp, nullable` | `null` | When visibility was changed (audit) |

**Relationship to existing columns:**

- `TenantUserMixin.user_id` = owner (who created it). Single purpose: ownership.
- `TenantUserMixin.tenant_id` = organizational scope. Single purpose: tenant boundary.
- `ShareableMixin.visibility` = access scope. Single purpose: who can see it.
- `ShareableMixin.shared_by` / `shared_at` = audit trail for sharing actions. Not ownership.

No column serves dual purposes.

### 3.3 Visibility Levels

| Level | Meaning | Read access | Write access |
|---|---|---|---|
| `private` | Only the owner can see it | Owner only | Owner only |
| `app` | All users with access to this app in the tenant can see it | Any user with app access | Owner, subject to route-level edit permission |

**System defaults are a special seeded case, not a third user-selectable visibility level.**
- System rows live in `SYSTEM_TENANT_ID` with `user_id = SYSTEM_USER_ID`
- System rows use the same `app` sharing semantics at read time, but remain immutable
- UI renders them as `System` based on system ownership, not because `visibility` has a third value
- No separate `is_built_in` or `is_global` flags remain

### 3.4 Which Entities Get ShareableMixin

**Gets ShareableMixin:**
- `evaluators` — replaces `is_global`, `is_built_in`, `forked_from` with the unified model
- `settings` — enables shared app contracts and other non-secret app configuration
- `prompts` — shareable prompt templates
- `schemas` — shareable output schemas

**Special-case within `settings`:**
- `llm-settings` remains private-only in v1
- `llm-settings` continues to live at `app_id=""`
- sharing UI must not be shown for `llm-settings`
- this preserves the current backend credential lookup contract and repo invariant

**Does NOT get ShareableMixin (always private, user-scoped):**
- `eval_runs` — execution artifacts belong to the user who ran them
- `chat_sessions`, `chat_messages` — conversation data is private
- `api_logs` — diagnostic data is private
- `jobs` — transient execution state
- `thread_evaluations`, `adversarial_evaluations` — child records of eval_runs, scoped through parent
- `users`, `tenants`, `roles` — managed by auth system

### 3.5 Evaluator Model Changes

**Columns removed:** `is_global`, `is_built_in`, `show_in_header`

**Columns added:** `visibility`, `forked_from` (already exists, kept), `shared_by`, `shared_at`, `linked_rule_ids` (JSON array of rule IDs from the app's catalog)

**Data migration (destructive, clean setup):**
- Drop and recreate evaluators table with new schema
- Re-seed system evaluators in `SYSTEM_TENANT_ID` with `visibility: 'app'`, `user_id: SYSTEM_USER_ID`
- `show_in_header` is removed — the main metric star (★) in the schema builder replaces it

### 3.6 Settings Table Changes

**Columns reworked:**
- `user_id` stays and continues to mean owner / creator
- Add `updated_by` — who last modified
- Add `visibility` — `'private'` (only creator sees) or `'app'` (all app users see)
- Add `forked_from`, `shared_by`, `shared_at` — standard ShareableMixin columns

**Deterministic uniqueness rules:**
- Private setting row: unique on `(tenant_id, app_id, key, user_id)` where `visibility = 'private'`
- Shared app row: unique on `(tenant_id, app_id, key, visibility)` where `visibility = 'app'`
- System default row: unique on `(tenant_id, app_id, key, visibility)` inside `SYSTEM_TENANT_ID`, where `visibility = 'app'`

This guarantees there is at most one app-shared winner for a given `(tenant, app, key)`.

**Resolution order when loading a setting:**
1. User's private override (`visibility: 'private'`, `user_id: current_user`) → use it
2. App-shared setting (`visibility: 'app'`) → use it
3. System default (`tenant_id: SYSTEM_TENANT_ID`, `visibility: 'app'`) → use it
4. Nothing → error or empty state

**Key-specific rule:**
- `key = 'llm-settings'` is always private-only and always loaded from `(tenant_id, user_id, app_id="")`
- `key = 'rule-catalog'` is an app-scoped shared setting in v1 and is the published runtime source for evaluator rules
- `key = 'adversarial-config'` is an app-scoped shared setting in v1
- shared settings are for app contracts and similar non-secret configuration, not credentials

### 3.7 Default Visibility Per Asset Type

Defined in app config (`appConfig.assetDefaults`), not hardcoded in entity models:

```
evaluator:              private    (user creates, shares when ready)
prompt:                 private
schema:                 private
adversarial_contract:   app        (shared by default — team contract)
llm_settings:           private    (personal API keys, never shareable in v1)
```

When creating an asset, the system reads the default from app config. The user or admin can change it if RBAC permits.

### 3.8 Prompt and Schema Versioning Model

**Decision:** Prompts and schemas become shareable without introducing a separate asset-family table in v1.

**Core model:**
- Each saved prompt/schema row is both:
  - a shareable asset version
  - an immutable library entry
- Editing content creates a new row rather than mutating the existing row in place
- `branch_key` identifies the version family / library entry
- `forked_from` points to the exact source version row, not to an abstract family ID

**Why this model:**
- Upstream: current settings UIs already treat prompt/schema edits as "save as new version"
- Downstream: frontend can keep using concrete row IDs for active prompt/schema selection without adding a new indirection layer

**Version branches:**
- Versions increment within one `branch_key`
- `branch_key` is created once when a prompt/schema library entry is first created
- Saving a new version of an existing asset keeps the same `branch_key` and increments `version`
- Forking a shared/system asset creates a new `branch_key` with `version = 1`
- System defaults use their own seeded `branch_key` values in `SYSTEM_TENANT_ID` and remain immutable

**Edit behavior:**
- Editing your own private or shared prompt/schema creates the next version in the same `branch_key`
- `PATCH /visibility` changes sharing metadata on the latest version row only; it does not create a new content version
- Editing a shared/system prompt/schema without shared edit permission uses **Save as Mine**, which creates a new private row with a new `branch_key`, `version = 1`, and `forked_from` set

**Default semantics:**
- `is_default` remains reserved for seeded system defaults
- shared tenant-created prompts/schemas do not reuse `is_default`
- a prompt/schema being shared does not make it active for everyone

**Active selection remains private:**
- `activePromptIds` and `activeSchemaIds` continue to live in the user's private `llm-settings` row
- sharing expands library visibility, not active selection

**UI implication:**
- PromptsTab and SchemasTab continue grouping by `prompt_type` and `source_type`
- list endpoints return the latest row per `branch_key` by default so the library shows one current entry per branch
- version history views can request full branch history explicitly
- tabs add visibility/owner metadata and share/fork actions, but keep "save as new version" semantics

---

## 4. App Config Schema

### 4.1 Core Concept

App identity and capabilities are defined as data (a config JSON on each app record), not as code branches. Components read feature flags from config. No component ever checks `appId === "string"`.

### 4.2 Storage

Add a `config` JSONB column to the existing `apps` table. Served to the frontend via app slug, not UUID, because frontend app identity is already slug-based.

- `GET /api/apps` continues listing active apps
- `GET /api/apps/:slug/config` returns the config payload for one app
- `appStore` is expanded to cache config by app slug while still tracking the current app slug

### 4.3 Config Shape

```
{
  "displayName": string,           // "Kaira Bot", shown in UI
  "icon": string,                  // icon key from shared icon set
  "description": string,           // subtitle text

  "features": {
    "hasRules": boolean,           // rules step in evaluator wizard
    "hasRubricMode": boolean,      // rubric builder toggle in wizard
    "hasCsvImport": boolean,       // CSV import button on evaluators page
    "hasAdversarial": boolean,     // adversarial testing tab/flow
    "hasTranscription": boolean,   // transcription config in eval setup
    "hasBatchEval": boolean,       // batch evaluation support
    "hasHumanReview": boolean      // human review workflow
  },

  "rules": {
    "catalogSource": string,       // "settings" in v1
    "catalogKey": string,          // "rule-catalog"
    "autoMatch": boolean           // enables draft-time rule auto-match
  },

  "evaluator": {
    "defaultVisibility": string,   // "private" or "app"
    "defaultModel": string,        // "gemini-2.5-flash"
    "variables": [                 // drives the variable picker
      {
        "key": string,             // "chat_transcript"
        "displayName": string,     // "Chat Transcript"
        "description": string,     // "Full conversation history"
        "category": string         // "Conversation"
      }
    ],
    "dynamicVariableSources": {
      "registry": boolean,         // enables GET /api/evaluators/variables
      "listingApiPaths": boolean   // enables GET /api/evaluators/variables/api-paths
    }
  },

  "assetDefaults": {
    "evaluator": string,           // default visibility for new evaluators
    "prompt": string,
    "schema": string,
    "adversarial_contract": string,
    "llm_settings": string
  },

  "evalRun": {
    "supportedTypes": string[]     // ["full_evaluation", "batch_thread", ...]
  }
}
```

### 4.4 Seed Configs for Current Apps

**Voice Rx:**
- `hasRules: false`, `hasRubricMode: false`, `hasCsvImport: false`
- `hasAdversarial: false`, `hasTranscription: true`
- Static variables: `transcript`, `sourceType`
- Dynamic variable sources: `registry: true`, `listingApiPaths: true`
- Asset defaults: all private

**Kaira Bot:**
- `hasRules: true`, `hasRubricMode: false`, `hasCsvImport: false`
- `hasAdversarial: true`, `hasTranscription: false`
- Rules metadata: `catalogSource: 'settings'`, `catalogKey: 'rule-catalog'`, `autoMatch: true`
- Static variables: `chat_transcript`, `session_metadata`
- Dynamic variable sources: `registry: true`, `listingApiPaths: false`
- Asset defaults: `adversarial_contract: 'app'`, rest private

**Inside Sales:**
- `hasRules: false`, `hasRubricMode: true`, `hasCsvImport: true`
- `hasAdversarial: false`, `hasTranscription: true`
- Static variables: `transcript`, `call_metadata`, `agent_name`
- Dynamic variable sources: `registry: true`, `listingApiPaths: false`
- Asset defaults: all private

### 4.5 Frontend Consumption

A `useAppConfig(appId)` hook reads from `appStore`. Components use it for all capability checks:

- Wizard step list: `steps.push(config.features.hasRules && 'rules')`
- Rule catalog bootstrap: `config.rules.*`
- Build mode toggle: `config.features.hasRubricMode && showRubricOption`
- CSV import button: `config.features.hasCsvImport && showCsvButton`
- Static variable picker data: `config.evaluator.variables`
- Dynamic variable fetches: `config.evaluator.dynamicVariableSources.*`
- Display name in headers: `config.displayName`

### 4.6 What App Config Does NOT Replace

App-specific execution logic stays as code. Transcription pipelines, LSQ integrations, Voice Rx two-call order — these are legitimate behavioral differences that belong in service-layer code, not in a config flag. App config drives UI capabilities, catalog metadata, and asset defaults only.

**App config does not carry volatile runtime catalogs.**
- The full rule catalog is fetched from the backend rules service, not embedded in `apps.config`
- In v1 the backend rules service reads the published app catalog from the app-scoped shareable setting row `key='rule-catalog'`
- This lets source systems publish new rules for immediate testing without code changes or app-config rewrites

---

## 5. RBAC Integration

### 5.1 Core Rule

```
Can THIS USER do THIS ACTION on THIS ASSET given its VISIBILITY?
```

### 5.2 Permission Matrix

Route handlers keep their existing asset-family permissions. `can_access()` is added after that gate and answers only the ownership / visibility question.

| Action | Upstream route requirement | Ownership / visibility rule |
|---|---|---|
| Read | Authenticated user with app access | Owner can read private; any app user can read `app`; system rows in `SYSTEM_TENANT_ID` are readable to any app user |
| Create | Existing create permission for that asset family | New row may be private or shared (`app`) based on defaults and permission |
| Edit | Existing edit permission for that asset family | Owner can edit private; shared edit depends on asset family permission + ownership rules |
| Delete | Existing delete permission for that asset family | Owner can delete private; shared delete requires delete permission and follows system immutability |
| Share / Unshare | Same permission as edit for that asset family | Only owner (or admin for selected asset families) can change visibility |
| Fork | Existing create permission for that asset family | Any user who can read a shared/system asset may fork it to private |

System assets (`user_id = SYSTEM_USER_ID`) are immutable. No one edits or deletes them. Anyone can read and fork them.

**Asset-family permission mapping in v1:**
- Evaluators, prompts, schemas: existing `resource:create`, `resource:edit`, `resource:delete`
- Settings, rule catalog, and adversarial contract writes: existing `settings:edit`
- Evaluation execution: unchanged, still uses `eval:run`

### 5.3 Implementation

One function: `can_access(user, asset, action) → bool`. Called inside route handlers after the existing auth middleware and permission decorators have passed.

- Route-level decorator: "Is this user authenticated, do they have app access, and do they have the correct asset-family permission?" (existing pattern, preserved)
- `can_access` call inside the handler: "Can this user do this specific action on this specific asset?" (new)

No new permission strings are introduced in v1. The harmonization layer reuses existing route permissions and adds only ownership/visibility checks.

### 5.4 Query Patterns

**Listing assets the user can see:**

Filter with: `((tenant_id == current_tenant) AND ((user_id == current_user) OR (visibility == 'app'))) OR (tenant_id == SYSTEM_TENANT_ID)` — within the app boundary.

For endpoints that must display owner metadata in the response, a lightweight join to `users` is allowed. The "no joins" simplification is not a hard requirement when the UI explicitly needs owner display name.

**Loading a setting with resolution:**

1. Query for `user_id == current_user, visibility == 'private'` → if found, return
2. Query for `visibility == 'app'` → if found, return
3. Query for `tenant_id == SYSTEM_TENANT_ID, visibility == 'app'` → if found, return
4. Return error/empty

Three queries maximum, usually hits on step 1 or 2.

### 5.5 Solving Existing Permission Problems

**Adversarial config read access:** The GET endpoint currently requires `settings:edit`. With the new model, the contract is `visibility: 'app'`, so any user with app access can read it. The PUT endpoint keeps `settings:edit` as the upstream permission and then applies `can_access(user, contract, 'edit')`.

**New user onboarding:** A new user assigned to an app immediately sees all shared evaluators, shared prompts, shared schemas, and shared contracts. Their runs stay private. If they lack private LLM credentials, they still need to configure those before running flows that require user-scoped API keys.

---

## 6. Sharing UX

### 6.1 At Creation Time

The evaluator wizard Step 1 includes a visibility radio:
- `(•) Just me` → `visibility: 'private'`
- `( ) Shared with app` → `visibility: 'app'`

Default comes from `appConfig.assetDefaults`. "Shared with app" is shown only when the user has the create/edit permission required for that asset family.

For prompts and schemas, the equivalent control appears in the save flow:
- **Save as Mine** → private branch/version
- **Save to Shared Library** → shared branch/version, only if the user has the relevant edit permission

### 6.2 On Existing Assets (Table Row Actions)

The ⋮ menu on each evaluator table row includes:
- **Share with app** — shown if asset is private AND user has the relevant edit permission. One click, confirmation toast.
- **Make private** — shown if asset is shared AND user is owner or admin. One click.
- **Fork (copy)** — shown on shared/system assets the user doesn't own. Creates a private copy with `forked_from` pointing back.

No modal, no approval workflow. The permission gate is the approval.

Prompts and schemas use the same concepts with version-aware labels:
- **Save as Mine** forks shared/system into a private branch
- **Save to Shared Library** creates the next shared version when allowed

### 6.3 Visual Indicators

**Table columns:** Visibility (icon + label) and Owner (username or "System").

| Visibility | Icon | Meaning |
|---|---|---|
| Private | 🔒 | Only you can see this |
| Shared (app) | 🔗 | All app users can see this |
| System | 🏛 | Built-in default, read-only |

These are rendered by a generic `VisibilityBadge` component in `src/components/ui/`.

### 6.4 Settings Pages

For settings that are shareable (adversarial contracts), a banner at the top shows ownership status:
- "🔗 Shared with all [app name] users · Last updated by [name] · [date]"
- "Save" writes to the shared copy (if permitted)
- "Save as Mine" forks to a private copy (if user lacks edit permission on shared)

LLM settings do not show this banner because they are private-only in v1.

### 6.5 Filter Tabs on Evaluators Page

| Tab | Filter |
|---|---|
| All | Everything the user can see (private + shared + system) |
| Shared | tenant rows with `visibility: 'app'` plus system seeded rows |
| Mine | `user_id: current_user` (both private and shared-by-me) |

---

## 7. Route and API Changes

### 7.1 New Endpoints

| Endpoint | Purpose |
|---|---|
| `PATCH /api/evaluators/:id/visibility` | Change visibility (share/unshare) |
| `POST /api/evaluators/:id/fork` | Fork a shared/system evaluator to private |
| `PATCH /api/prompts/:id/visibility` | Change prompt visibility |
| `POST /api/prompts/:id/fork` | Fork a shared/system prompt version to private |
| `PATCH /api/schemas/:id/visibility` | Change schema visibility |
| `POST /api/schemas/:id/fork` | Fork a shared/system schema version to private |
| `PATCH /api/settings/:id/visibility` | Change visibility for shareable settings |
| `POST /api/settings/:id/fork` | Fork a shared setting to a private copy |
| `GET /api/rules` | Get the published rule catalog for one app |
| `PUT /api/rules` | Publish/update the rule catalog for one app |
| `GET /api/apps/:slug/config` | Get app config (features, variables, asset defaults) |

### 7.1a New Job Handler

| Job type | Purpose |
|---|---|
| `generate-evaluator-draft` | Generate schema suggestions and rule matches from prompt text via LLM |

### 7.2 Modified Endpoints

| Endpoint | Change |
|---|---|
| `GET /api/evaluators` | Add `visibility` filter param. Return visibility + owner fields (`ownerId`, `ownerName`). Query includes shared assets, not just user's own. |
| `POST /api/evaluators` | Accept `visibility` field. Apply `can_access` check. |
| `PUT /api/evaluators/:id` | Apply `can_access(user, evaluator, 'edit')` check. |
| `DELETE /api/evaluators/:id` | Apply `can_access(user, evaluator, 'delete')` check. |
| `GET /api/adversarial-config` | Remove `settings:edit` requirement for read. Check `can_access(user, config, 'read')` instead. |
| `PUT /api/adversarial-config` | Check `can_access(user, config, 'edit')`. |
| `GET /api/settings` | Default to returning resolved winners for a given `(app_id, key)`: private → app → system. `includeAll=true` returns all visible rows when a settings management UI needs the raw records. |
| `PUT /api/settings` | Accept `visibility`. Check `can_access`. Upsert private or app-shared settings according to the deterministic uniqueness rules. |
| `GET /api/prompts` | Include shared + system rows, plus visibility/owner metadata, while preserving `prompt_type` and `source_type` filters. Return latest row per `branch_key` by default; `includeVersions=true` returns full history. |
| `POST /api/prompts` | Continue to mean "create a new version row." Accept `visibility` and branch rules described in Section 3.8. |
| `PUT /api/prompts/:id` | Deprecated for content edits in v1. If retained temporarily, limit to metadata-only updates. |
| `GET /api/schemas` | Include shared + system rows, plus visibility/owner metadata, while preserving `prompt_type` and `source_type` filters. Return latest row per `branch_key` by default; `includeVersions=true` returns full history. |
| `POST /api/schemas` | Continue to mean "create a new version row." Accept `visibility` and branch rules described in Section 3.8. |
| `PUT /api/schemas/:id` | Deprecated for content edits in v1. If retained temporarily, limit to metadata-only updates. |

### 7.3 Deprecated Patterns

- `evaluator.isGlobal` / `evaluator.isBuiltIn` — replaced by `visibility` + system ownership (`tenant_id == SYSTEM_TENANT_ID`, `user_id == SYSTEM_USER_ID`)
- `evaluator.showInHeader` — replaced by `isMainMetric` + `role: 'metric'` in output schema
- `displayMode: 'header' | 'card' | 'hidden'` — replaced by `role: 'metric' | 'detail' | 'reasoning'`
- `isRubricMode = appId === "inside-sales"` — replaced by `appConfig.features.hasRubricMode`
- Any `if (appId === "x")` check in shared components — replaced by `appConfig.features.*`

---

## 8. Database Model Changes

### 8.1 Approach

No migrations. Drop and recreate tables that need structural changes. Re-seed all default data. The platform is pre-launch with no production data to preserve.

### 8.2 apps Table

Add `config` JSONB column. Seed with per-app config as defined in Section 4.4.

### 8.3 evaluators Table

Remove: `is_global`, `is_built_in`, `show_in_header`
Add: `visibility` (enum, default 'private'), `shared_by` (FK users, nullable), `shared_at` (timestamp, nullable), `linked_rule_ids` (JSON array, default empty)
Keep: `forked_from` (already exists)
Rename: nothing — `user_id` stays as owner via TenantUserMixin

### 8.4 settings Table

Add: `updated_by` (FK users, nullable), `visibility` (enum, default 'private'), `forked_from` (same type as settings PK, nullable), `shared_by` (FK users, nullable), `shared_at` (timestamp, nullable)
Keep: `user_id` as owner / creator
Replace the single unique constraint with deterministic private/shared uniqueness rules from Section 3.6
Published rule catalogs in v1 are stored here as app-scoped shared rows with `key='rule-catalog'`

### 8.5 prompts Table

Keep: `version`, `prompt_type`, `source_type`, `is_default`, `user_id`
Add: `branch_key`, `visibility`, `forked_from`, `shared_by`, `shared_at`
Replace the current unique constraint with branch-aware version uniqueness on `(tenant_id, app_id, prompt_type, source_type, branch_key, version)`
Behavioral rule: prompt content edits create new version rows; system defaults stay immutable

### 8.6 schemas Table

Keep: `version`, `prompt_type`, `source_type`, `is_default`, `user_id`
Add: `branch_key`, `visibility`, `forked_from`, `shared_by`, `shared_at`
Replace the current unique constraint with branch-aware version uniqueness on `(tenant_id, app_id, prompt_type, source_type, branch_key, version)`
Behavioral rule: schema content edits create new version rows; system defaults stay immutable

### 8.7 New: ShareableMixin

Applied to: evaluators, settings, prompts, schemas

Provides: `visibility`, `forked_from`, `shared_by`, `shared_at`

### 8.8 Seed Data

System evaluators: rows in `SYSTEM_TENANT_ID` with `visibility: 'app'`, `user_id: SYSTEM_USER_ID`
System settings: rows in `SYSTEM_TENANT_ID` with `visibility: 'app'`, `user_id: SYSTEM_USER_ID`
System prompts/schemas: rows in `SYSTEM_TENANT_ID` with `visibility: 'app'`, `user_id: SYSTEM_USER_ID`, `is_default: true`
App configs: seeded into `apps.config` column

---

## 9. Decision Trace Map

| Decision | Upstream constraint | Downstream impact |
|---|---|---|
| LLM settings remain private-only | Runtime credential lookup already resolves `llm-settings` by `(tenant_id, user_id, app_id="")`, and the repo invariant requires per-user storage | No sharing UI for LLM settings, no shared credential onboarding flow, `settings_helper` contract stays intact |
| System defaults remain in the system tenant | Current readers already resolve seeded defaults through `SYSTEM_TENANT_ID` / `SYSTEM_USER_ID` | Queries, seeders, and UI badges use one system-asset model instead of inventing a third tenant visibility tier |
| Variable picker is hybrid static + dynamic | Voice Rx currently needs listing-derived API response paths in addition to app-wide variables | `appConfig` stores static variables and dynamic source flags; `VariablePickerPopover` merges config data with backend-provided runtime variables |
| Rule catalogs are data-driven but not embedded in app config | Rule catalogs are volatile runtime content and need external/source-system updates without code changes | App config carries only metadata; backend rules API serves the published catalog from app-scoped settings |
| Prompt/schema sharing uses immutable version rows plus `branch_key` | Existing prompt/schema editors already save as new versions instead of mutating built-ins, but `prompt_type` alone cannot identify multiple library entries | Routes keep `POST` as version creation, active prompt/schema IDs stay private user settings, and versioning becomes deterministic |
| Output schema v2 cutover is atomic | Reports, eval-run rendering, exports, seeds, and editor UIs still consume `displayMode` | All readers must be updated before writers switch; reseeding is part of the rollout |
| Owner name is returned on evaluator list endpoints | UI requires an Owner column, but current responses only expose owner IDs | `GET /api/evaluators` and similar library endpoints may use a lightweight join to return `ownerName` |
| App config is fetched by slug | Frontend app identity and routing already use app slugs, not app UUIDs | `appStore` caches config by slug; route shape becomes `GET /api/apps/:slug/config` |
| Shared settings need deterministic uniqueness and a resolved-read contract | Settings resolution assumes a single app-shared winner per `(tenant, app, key)` | Settings table replaces one broad unique constraint with private/shared uniqueness rules so `GET /api/settings` is deterministic |
| Prompt-driven draft generation uses the job system | Repo architecture says multi-second LLM work should run as jobs | Wizard assistance uses `submitAndPollJob()` and a dedicated `generate-evaluator-draft` handler instead of ad hoc synchronous extraction endpoints |

---

## 10. Component Inventory

### 10.1 New Shared Components (src/components/ui/)

| Component | Purpose |
|---|---|
| `VisibilityBadge` | Renders 🔒/🔗/🏛 icon with label |
| `VisibilityToggle` | Radio group for private/shared in forms |
| `StarToggle` | ★/☆ main metric pin for schema table |
| `RoleBadge` | Colored badge for metric/detail/reasoning |

### 10.2 New Feature Components

| Component | Purpose |
|---|---|
| `EvaluatorsTable` | Replaces card grid. Shared across all apps. |
| `EvaluatorExpandRow` | Expanded row showing field details |
| `CreateEvaluatorWizard` | Unified wizard replacing CreateEvaluatorOverlay |
| `SchemaTable` | Output fields table with roles, star, thresholds |
| `RulePicker` | Secondary overlay for selecting rules from catalog |
| `BuildModeToggle` | "Write Prompt" / "Use Rubric" switch |
| `ShareMenuItem` | ⋮ menu item for share/unshare actions |
| `OwnershipBanner` | "Shared by X · date" strip for settings pages |
| `VersionLibraryActions` | Shared action cluster for prompt/schema save-as-mine / save-to-shared / fork flows |

### 10.3 Retired Components

| Component | Replaced by |
|---|---|
| `EvaluatorCard` | `EvaluatorsTable` + `EvaluatorExpandRow` |
| `EvaluatorsView` (Voice Rx variant) | `EvaluatorsTable` |
| `KairaBotEvaluatorsView` | `EvaluatorsTable` |
| `EvaluatorRegistryPicker` | Filter tabs (All/Shared/Mine) + `ForkButton` in ⋮ menu |
| `OutputSchemaBuilder` (standalone) | `SchemaTable` |
| `InlineSchemaBuilder` | `SchemaTable` |

### 10.4 Preserved Components

| Component | Status |
|---|---|
| `RubricBuilder` | Kept. Plugged into wizard as alternate build mode via `hasRubricMode` flag. |
| `VariablePickerPopover` | Kept. Data source changes from hardcoded app branches to config-directed static + dynamic sources. |
| `ArrayItemConfigModal` | Kept. Used by SchemaTable for array field configuration. |

---

## 11. Day-in-the-Life Narrative

Admin logs in, opens Kaira Bot, creates an adversarial contract with safety rules and empathy goals, and shares it with the app — every Kaira Bot user in the tenant can now see and use that contract for their evaluations. The same admin also shares a tuned evaluation prompt and schema library entry for Kaira adversarial runs. A new user joins the team, gets assigned to Kaira Bot, and on their first login they see the shared contract, the shared evaluators, and the shared prompt/schema library entries. Their active prompt/schema selections remain their own, and their LLM credentials remain private, but they can immediately fork the shared library items they want to use. After running a few evaluations (which only they can see), they build a custom evaluator for date handling accuracy, test it on a few runs, and once they're happy with it, share it with the app so the rest of the team can use it too. Another team member sees that shared evaluator, likes the idea but wants to tweak the thresholds, so they fork it — now they have their own private copy while the original stays untouched for everyone else. The admin later updates the adversarial contract to add a new safety rule, and the next time anyone runs an evaluation, they pick up the updated contract automatically. When the admin improves the shared prompt, that creates a new shared prompt version; no user's active selection changes until they explicitly choose that new version.

---

## 12. RBAC and Asset UX Addendum

This addendum does not introduce new behavior. It restates the designed v1 model in user-flow form so implementation planning, API work, and UI work all target the same behavior.

### 12.1 Asset Concepts in Plain Language

- **Private asset** — owned by one user and visible only to that user
- **App-shared asset** — owned by one user but readable by any user with access to that app in the same tenant
- **System asset** — seeded immutable row in `SYSTEM_TENANT_ID`, readable by any user with app access, forkable but never editable in place

These are not three equal visibility tiers. Only `private` and `app` are user-selectable `visibility` values. "System" is derived from system ownership (`tenant_id == SYSTEM_TENANT_ID`, `user_id == SYSTEM_USER_ID`).

### 12.2 Role Model in Plain Language

The harmonization design does not add new permission strings in v1. It reuses the current route-level RBAC model:

- App access decides whether the user can enter an app and read app-scoped shared/system assets
- `resource:create/edit/delete` governs evaluators, prompts, and schemas
- `settings:edit` governs shared app contracts, including adversarial config and rule catalog publishing
- `eval:run` continues to govern evaluation execution

Then `can_access(user, asset, action)` applies ownership and visibility rules on top of those permissions.

### 12.3 T0 State After Rollout

Immediately after rollout and reseeding, before any tenant user shares anything:

- Users see seeded system evaluators, prompts, and schemas in the shared library views
- Users do not see any tenant-shared assets unless an admin or member has explicitly shared them
- Users do not inherit anyone else's `llm-settings`; provider credentials remain private-only
- If Kaira has a published shared `adversarial-config` or `rule-catalog`, users with app access can read them immediately

UX implication:
- `All` = system assets + tenant shared assets + the user's own private assets
- `Shared` = system assets + tenant shared assets
- `Mine` = only assets owned by the current user

### 12.4 Admin Sharing Flow

Example: an admin prepares Kaira for the rest of the team.

1. Admin opens Kaira and has app access plus the existing `settings:edit` and `resource:*` permissions required for setup.
2. Admin publishes `adversarial-config` and `rule-catalog` as app-shared settings.
3. Admin creates or updates evaluators, prompts, and schemas.
4. For evaluators, admin uses **Share with app**.
5. For prompts and schemas, admin uses **Save to Shared Library**.
6. Those assets now appear in `Shared` for every Kaira user in that tenant.

Important constraints:
- Sharing changes visibility; it does not transfer ownership
- System assets are never edited in place; admin must fork before customizing if starting from a system default
- A new prompt/schema version in a shared branch does not silently change another user's active selection

### 12.5 New User Personal Flow

Example: a new member is granted access to Kaira after the admin setup above.

1. User is assigned app access to Kaira.
2. On first login, the user sees:
   - system evaluators, prompts, schemas
   - tenant-shared evaluators, prompts, schemas
   - shared adversarial config
   - published shared rule catalog
3. The user still must configure private `llm-settings` before LLM-backed flows can run under their account.
4. The user can use a shared evaluator as-is, or click **Fork** to create a private copy.
5. The forked asset appears in `Mine` with the new user as owner and `visibility='private'`.
6. The user can iterate privately without affecting the shared source asset.
7. If their role has the existing create/edit permissions, they can later share their private evaluator back to the app.

### 12.6 Ownership and Edit Rules by Asset Type

**Evaluators, prompts, schemas**
- Owner can edit/delete private assets if they have the existing route permission
- Any app user can read app-shared assets
- Editing another user's app-shared asset is not granted just because it is shared; shared edit still follows route permission plus ownership rules
- Fork is the standard path for "I want my own version of this shared/system asset"

**Settings-backed shared contracts**
- `adversarial-config` and `rule-catalog` are app-scoped shared settings in v1
- Read access follows app access plus resolved visibility
- Write/publish access remains behind existing `settings:edit`
- `llm-settings` is explicitly excluded and always remains private-only

### 12.7 UX Summary

The intended experience is:

- **System** provides built-in starting points
- **Shared** is the team's reusable library
- **Mine** is the user's safe workspace

The product does not introduce a new hidden governance model beyond that. Admins curate shared app contracts and shared library assets; users discover those immediately once they have app access; users personalize by forking or creating private assets; and all LLM credentials remain strictly personal.
