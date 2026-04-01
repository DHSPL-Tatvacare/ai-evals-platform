# Platform Harmonization — Design Spec v1

**Date:** 2026-04-01
**Status:** Approved direction, pending implementation planning
**Scope:** Evaluator UI unification, asset ownership model, app config schema, RBAC integration

---

## 1. Problem Statement

The platform has three apps (Voice Rx, Kaira Bot, Inside Sales) that evolved independently. Each has its own evaluator UI patterns, wizard flows, and hardcoded branches. Settings and assets are user-scoped with no sharing mechanism, meaning team members operate in isolation — each configuring their own LLM keys, seeing only their own runs, and unaware of each other's evaluators or contracts. App identity is scattered across code as string checks (`if appId === "inside-sales"`), making it impossible to onboard a new app without code changes.

The platform is pre-launch. No production data to preserve. Clean structural changes are preferred over backward-compatible migrations.

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
2. **Schema** — Output fields table. If coming from "Write Prompt" mode, the system calls an LLM endpoint to extract fields before showing this step. If coming from "Use Rubric" mode, fields are pre-populated from the rubric. Either way, the same schema table component renders and the user can edit.
3. **Rules** — Only shown if `appConfig.features.hasRules` is true. Auto-matches rules from the app's catalog against the evaluator prompt content via LLM. User can add/remove via a rule picker secondary overlay. If this step doesn't exist, the Schema step footer shows "Save Evaluator."

**Build mode toggle behavior:**
- "Write Prompt" → user writes prompt → on Next, LLM extracts schema → schema table shown
- "Use Rubric" → user builds rubric (dimensions, checks, compliance gates, thresholds) → RubricBuilder auto-generates prompt + schema → schema table shown pre-filled

Both paths converge on the same schema table. The schema table is the single source of truth for output field definitions.

### 2.3 Schema Table: Simplified Display Model

**Decision:** The old `displayMode` (header/card/hidden) column is removed. Role determines visibility.

**Roles:**
- `metric` — Visible in table row (expanded) and eligible to be pinned as main metric (★). Thresholds shown for number types.
- `detail` — Visible in expanded row only. Boolean gates, sub-scores, flags.
- `reasoning` — Hidden from UI entirely. Internal audit trail. Row visually dimmed in the schema builder.

**Main metric (★):** A star icon on each row. Only one can be active per evaluator. Only clickable on `metric` role fields. The pinned field's value shows in the Main Metric column of the evaluators table.

### 2.4 Extract from Prompt: LLM-Powered Schema Generation

**Decision:** When the user moves from Prompt → Schema step, the system calls a backend endpoint that sends the prompt to the configured LLM and returns `EvaluatorOutputField[]`.

**Endpoint:** `POST /api/evaluators/extract-schema`
- Input: `{ prompt: string, appId: string }`
- Output: `EvaluatorOutputField[]` with keys, types, roles, descriptions, thresholds inferred from prompt content
- Uses a meta-prompt: "Given this evaluation prompt, identify the expected output fields and return them as structured JSON with key, type, role, description, and suggested thresholds."

**Behavior:**
- Runs automatically on transition from Prompt → Schema step
- Shows a loading state: "Extracting output schema from prompt…"
- User can click "Skip — build manually" to bypass
- After extraction, a banner shows: "Extracted N fields from prompt — review and adjust below"
- "Re-extract" button available if user goes back and edits the prompt
- The LLM understands patterns like "Rate 1-5" → number + metric + thresholds, "yes/no" → boolean + detail, "reasoning/explanation" → text + reasoning

**This replaces** the idea of client-side heuristic parsing. LLM extraction is more reliable and handles diverse prompt styles.

### 2.5 Rule Picker: Generic, Prop-Driven

**Decision:** The rule picker is a generic component that receives rules as data, not an app-specific feature.

**Component:** `<RulePicker rules={appRules} selected={linkedRuleIds} onChange={setLinkedRuleIds} />`

- Opens as a secondary overlay on top of the primary wizard overlay
- Shows all rules from the app's catalog with search and tags
- Pre-checks auto-matched rules (matched via LLM comparison of prompt content vs rule descriptions)
- Auto-matched rules show an "auto" badge, user can remove them
- Rules are stored as references (IDs) on the evaluator, not copies. Rule updates in the catalog propagate to all evaluators using them.
- Rules are injected into the evaluation prompt at runtime as a "Rules to verify" section.

**Enabling rules for any app:** Set `appConfig.features.hasRules = true` and configure a rule catalog for that app. No code changes. The wizard step auto-appears, the picker auto-populates.

### 2.6 Variable Picker: App-Config Driven

**Decision:** Variables shown in the prompt editor come from `appConfig.evaluator.variables`, not hardcoded per app.

- Opens as a secondary overlay
- Variables grouped by category
- Clicking "Insert" places `{{variable}}` at cursor position in prompt textarea
- Same component for all apps, data differs based on app config

### 2.7 Frontend Architecture Rules

- All colors, spacing, typography from the existing design token system and component library. No hardcoded hex values, no inline styles for theming.
- All new components are generic and importable. No app-specific component files for shared patterns.
- `cn()` for all conditional class merging (Tailwind v4 JIT requirement).
- No `if (appId === "x")` in shared components. Feature checks go through `appConfig.features.*`.
- App display names read from `appConfig.displayName`, never hardcoded strings.
- Any net-new UI primitive (e.g., `VisibilityBadge`, `StarToggle`) is added to `src/components/ui/` as a generic component.

---

## 3. Asset Ownership Model

### 3.1 Core Concept

Every entity in the system is an asset with an ownership and visibility property. Ownership is always a user. Visibility determines who else can see and interact with the asset.

### 3.2 ShareableMixin

A new SQLAlchemy mixin applied to entities that support sharing. Added alongside the existing `TenantUserMixin` and `TimestampMixin`.

**Columns:**

| Column | Type | Default | Purpose |
|---|---|---|---|
| `visibility` | `enum('private', 'app', 'tenant')` | `'private'` | Who can see this asset |
| `forked_from` | `uuid, FK to same table, nullable` | `null` | Lineage — which asset was this copied from |
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
| `app` | All users with access to this app in the tenant can see it | Any user with app access | Owner or `settings:edit` permission |
| `tenant` | All users in the tenant can see it | Any tenant user | Owner or admin |

System assets (seeded defaults) are represented as `visibility: 'tenant'` + `user_id: SYSTEM_USER_ID`. No separate `is_built_in` or `is_global` flags.

### 3.4 Which Entities Get ShareableMixin

**Gets ShareableMixin:**
- `evaluators` — replaces `is_global`, `is_built_in`, `forked_from` with the unified model
- `settings` — enables shared contracts, shared LLM keys
- `prompts` — shareable prompt templates
- `schemas` — shareable output schemas

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
- Re-seed system evaluators with `visibility: 'tenant'`, `user_id: SYSTEM_USER_ID`
- `show_in_header` is removed — the main metric star (★) in the schema builder replaces it

### 3.6 Settings Table Changes

**Columns removed:** `user_id` as a scoping mechanism

**Columns reworked:**
- `user_id` renamed to `created_by` — purely attribution, who created this setting
- Add `updated_by` — who last modified
- Add `visibility` — `'private'` (only creator sees) or `'app'` (all app users see)
- Add `forked_from`, `shared_by`, `shared_at` — standard ShareableMixin columns

**Unique constraint changes:**
- Old: `(tenant_id, app_id, key, user_id)`
- New: `(tenant_id, app_id, key, visibility, created_by)` — allows both a shared version and per-user overrides to coexist

**Resolution order when loading a setting:**
1. User's private override (`visibility: 'private'`, `created_by: current_user`) → use it
2. App-shared setting (`visibility: 'app'`) → use it
3. System default (`tenant_id: SYSTEM_TENANT_ID`) → use it
4. Nothing → error or empty state

### 3.7 Default Visibility Per Asset Type

Defined in app config (`appConfig.assetDefaults`), not hardcoded in entity models:

```
evaluator:              private    (user creates, shares when ready)
prompt:                 private
schema:                 private
adversarial_contract:   app        (shared by default — team contract)
llm_settings:           private    (personal API keys)
```

When creating an asset, the system reads the default from app config. The user or admin can change it if RBAC permits.

---

## 4. App Config Schema

### 4.1 Core Concept

App identity and capabilities are defined as data (a config JSON on each app record), not as code branches. Components read feature flags from config. No component ever checks `appId === "string"`.

### 4.2 Storage

Add a `config` JSONB column to the existing `apps` table. Served to the frontend via `GET /api/apps/:id`. Cached in the frontend `appStore`.

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
    ]
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
- Variables: `transcript`, `sourceType`, API response paths
- Asset defaults: all private

**Kaira Bot:**
- `hasRules: true`, `hasRubricMode: false`, `hasCsvImport: false`
- `hasAdversarial: true`, `hasTranscription: false`
- Variables: `chat_transcript`, `session_metadata`
- Asset defaults: `adversarial_contract: 'app'`, rest private

**Inside Sales:**
- `hasRules: false`, `hasRubricMode: true`, `hasCsvImport: true`
- `hasAdversarial: false`, `hasTranscription: true`
- Variables: `transcript`, `call_metadata`, `agent_name`
- Asset defaults: all private

### 4.5 Frontend Consumption

A `useAppConfig(appId)` hook reads from `appStore`. Components use it for all capability checks:

- Wizard step list: `steps.push(config.features.hasRules && 'rules')`
- Build mode toggle: `config.features.hasRubricMode && showRubricOption`
- CSV import button: `config.features.hasCsvImport && showCsvButton`
- Variable picker data: `config.evaluator.variables`
- Display name in headers: `config.displayName`

### 4.6 What App Config Does NOT Replace

App-specific execution logic stays as code. Transcription pipelines, LSQ integrations, Voice Rx two-call order — these are legitimate behavioral differences that belong in service-layer code, not in a config flag. App config drives UI capabilities and asset defaults only.

---

## 5. RBAC Integration

### 5.1 Core Rule

```
Can THIS USER do THIS ACTION on THIS ASSET given its VISIBILITY?
```

### 5.2 Permission Matrix

| Action | Private asset | Shared asset (app/tenant) |
|---|---|---|
| Read | Owner only | Any user with app access |
| Create | Any user with app access | Any user (visibility set at creation per asset defaults) |
| Edit | Owner only | Owner OR user with `settings:edit` |
| Delete | Owner only | Owner OR admin |
| Share (private → app) | Owner AND `settings:edit` | n/a |
| Unshare (app → private) | Owner AND `settings:edit` | Owner AND `settings:edit` |
| Fork | n/a (already yours) | Any user with app access |

System assets (`user_id = SYSTEM_USER_ID`) are immutable. No one edits or deletes them. Anyone can read and fork them.

### 5.3 Implementation

One function: `can_access(user, asset, action) → bool`. Called inside route handlers after the existing auth middleware and permission decorators have passed.

- Route-level decorator: "Is this user authenticated and do they have app access?" (existing, unchanged)
- `can_access` call inside the handler: "Can this user do this specific action on this specific asset?" (new)

No new permission strings. Existing permissions (`eval:view`, `eval:run`, `settings:edit`, admin role) cover all scenarios because the visibility rules are universal across entity types.

### 5.4 Query Patterns

**Listing assets the user can see:**

Filter with: `(user_id == current_user) OR (visibility == 'app') OR (visibility == 'tenant') OR (user_id == SYSTEM_USER_ID)` — within the tenant and app boundary.

One query, no joins, no subqueries.

**Loading a setting with resolution:**

1. Query for `created_by == current_user, visibility == 'private'` → if found, return
2. Query for `visibility == 'app'` → if found, return
3. Query for `tenant_id == SYSTEM_TENANT_ID` → if found, return
4. Return error/empty

Three queries maximum, usually hits on step 1 or 2.

### 5.5 Solving Existing Permission Problems

**Adversarial config read access:** The GET endpoint currently requires `settings:edit`. With the new model, the contract is `visibility: 'app'`, so any user with app access can read it. The PUT endpoint checks `can_access(user, contract, 'edit')`, which requires owner or `settings:edit`.

**New user onboarding:** A new user assigned to an app immediately sees all shared evaluators, shared contracts, and shared LLM keys. They can run evaluations without configuring anything. Their runs are private. They can fork shared assets to customize.

---

## 6. Sharing UX

### 6.1 At Creation Time

The evaluator wizard Step 1 includes a visibility radio:
- `(•) Just me` → `visibility: 'private'`
- `( ) Shared with app` → `visibility: 'app'`

Default comes from `appConfig.assetDefaults`. "Shared with app" option only shown if user has `settings:edit` permission.

### 6.2 On Existing Assets (Table Row Actions)

The ⋮ menu on each evaluator table row includes:
- **Share with app** — shown if asset is private AND user has `settings:edit`. One click, confirmation toast.
- **Make private** — shown if asset is shared AND user is owner or admin. One click.
- **Fork (copy)** — shown on shared/system assets the user doesn't own. Creates a private copy with `forked_from` pointing back.

No modal, no approval workflow. The permission gate is the approval.

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

### 6.5 Filter Tabs on Evaluators Page

| Tab | Filter |
|---|---|
| All | Everything the user can see (private + shared + system) |
| Shared | `visibility: 'app'` or `visibility: 'tenant'` |
| Mine | `user_id: current_user` (both private and shared-by-me) |

---

## 7. Route and API Changes

### 7.1 New Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/evaluators/extract-schema` | LLM-powered schema extraction from prompt text |
| `PATCH /api/evaluators/:id/visibility` | Change visibility (share/unshare) |
| `POST /api/evaluators/:id/fork` | Fork a shared/system evaluator to private |
| `GET /api/apps/:id/config` | Get app config (features, variables, asset defaults) |

### 7.2 Modified Endpoints

| Endpoint | Change |
|---|---|
| `GET /api/evaluators` | Add `visibility` filter param. Return visibility + owner fields. Query includes shared assets, not just user's own. |
| `POST /api/evaluators` | Accept `visibility` field. Apply `can_access` check. |
| `PUT /api/evaluators/:id` | Apply `can_access(user, evaluator, 'edit')` check. |
| `DELETE /api/evaluators/:id` | Apply `can_access(user, evaluator, 'delete')` check. |
| `GET /api/adversarial-config` | Remove `settings:edit` requirement for read. Check `can_access(user, config, 'read')` instead. |
| `PUT /api/adversarial-config` | Check `can_access(user, config, 'edit')`. |
| `GET /api/settings` | Support resolution chain: private → app → system. |
| `PUT /api/settings` | Accept `visibility`. Check `can_access`. |

### 7.3 Deprecated Patterns

- `evaluator.isGlobal` / `evaluator.isBuiltIn` — replaced by `visibility` + `user_id == SYSTEM_USER_ID`
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

Remove: conceptual overloading of `user_id` as both owner and scope
Rename: `user_id` → `created_by`
Add: `updated_by` (FK users, nullable), `visibility` (enum, default 'private'), `forked_from` (uuid, nullable), `shared_by` (FK users, nullable), `shared_at` (timestamp, nullable)
Unique constraint: `(tenant_id, app_id, key, visibility, created_by)`

### 8.5 New: ShareableMixin

Applied to: evaluators, settings, prompts, schemas

Provides: `visibility`, `forked_from`, `shared_by`, `shared_at`

### 8.6 Seed Data

System evaluators: `visibility: 'tenant'`, `user_id: SYSTEM_USER_ID`
System settings: `visibility: 'tenant'`, `created_by: SYSTEM_USER_ID`
App configs: seeded into `apps.config` column

---

## 9. Component Inventory

### 9.1 New Shared Components (src/components/ui/)

| Component | Purpose |
|---|---|
| `VisibilityBadge` | Renders 🔒/🔗/🏛 icon with label |
| `VisibilityToggle` | Radio group for private/shared in forms |
| `StarToggle` | ★/☆ main metric pin for schema table |
| `RoleBadge` | Colored badge for metric/detail/reasoning |

### 9.2 New Feature Components

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

### 9.3 Retired Components

| Component | Replaced by |
|---|---|
| `EvaluatorCard` | `EvaluatorsTable` + `EvaluatorExpandRow` |
| `EvaluatorsView` (Voice Rx variant) | `EvaluatorsTable` |
| `KairaBotEvaluatorsView` | `EvaluatorsTable` |
| `EvaluatorRegistryPicker` | Filter tabs (All/Shared/Mine) + `ForkButton` in ⋮ menu |
| `OutputSchemaBuilder` (standalone) | `SchemaTable` |
| `InlineSchemaBuilder` | `SchemaTable` |

### 9.4 Preserved Components

| Component | Status |
|---|---|
| `RubricBuilder` | Kept. Plugged into wizard as alternate build mode via `hasRubricMode` flag. |
| `VariablePickerPopover` | Kept. Data source changes from hardcoded to `appConfig.evaluator.variables`. |
| `ArrayItemConfigModal` | Kept. Used by SchemaTable for array field configuration. |

---

## 10. Day-in-the-Life Narrative

Admin logs in, opens Kaira Bot, creates an adversarial contract with safety rules and empathy goals, and shares it with the app — every Kaira Bot user in the tenant can now see and use that contract for their evaluations. A new user joins the team, gets assigned to Kaira Bot, and on their first login they see the shared contract, the shared evaluators, and the admin's shared LLM keys — they can run an adversarial evaluation immediately without configuring anything. After running a few evaluations (which only they can see), they build a custom evaluator for date handling accuracy, test it on a few runs, and once they're happy with it, share it with the app so the rest of the team can use it too. Another team member sees that shared evaluator, likes the idea but wants to tweak the thresholds, so they fork it — now they have their own private copy while the original stays untouched for everyone else. The admin later updates the adversarial contract to add a new safety rule, and the next time anyone runs an evaluation, they pick up the updated contract automatically — no one had to reconfigure anything.
