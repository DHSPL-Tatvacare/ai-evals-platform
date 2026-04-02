# Platform Harmonization v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the platform harmonization design without deviating from the approved spec: unify evaluator UX, move assets to the private/app-shared model, make app capabilities DB-driven, add deterministic prompt/schema version branches, and cut over evaluator output handling from `displayMode` to role-based visibility.

**Architecture:** Treat this as a contract-first rollout. First land backend data contracts, access rules, app config, and shared-setting resolution; then update all readers to understand the new contracts; then replace legacy evaluator/settings UI with config-driven shared components. The rollout must preserve the repo invariants from `AGENTS.md`: no direct SDK calls outside provider abstractions, no component polling loops, no hardcoded app-name branches in shared UI, and no shared LLM credentials.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Pydantic/CamelModel, React, TypeScript, Zustand, repository-style frontend API clients, job polling via `submitAndPollJob()`

---

## Guardrails

- Keep `llm-settings` private-only at `(tenant_id, user_id, app_id="")`.
- Do not introduce a third user-selectable visibility tier. Only `private` and `app` are persisted visibility values.
- Keep system defaults in `SYSTEM_TENANT_ID` / `SYSTEM_USER_ID`; represent "System" in UI from ownership, not a third visibility enum.
- Do not embed live rule catalogs in `apps.config`; use DB-backed rule catalog storage plus a backend rules API.
- Do not switch evaluator writers to output-schema v2 until all known readers are updated.
- Do not hardcode app slugs in shared components. Feature checks must flow through app config.
- Preserve app-specific execution logic in service-layer code. App config is for UI capabilities, variable sources, defaults, and catalog metadata only.

## Phase Map

1. Backend data contracts and access primitives
2. Shared settings, app config, and rules service
3. Prompt/schema branch model and versioned library APIs
4. Evaluator API harmonization and output-schema v2 backend cutover
5. Frontend app config/data-layer reshaping
6. Evaluator UX replacement: table, wizard, schema table, rule picker
7. Prompt/schema/adversarial shared-library UX
8. Seed refresh, guide/doc cleanup, and full verification

## File Map

### Backend models / schemas / routes

- Modify: `backend/app/models/app.py`
- Modify: `backend/app/models/evaluator.py`
- Modify: `backend/app/models/setting.py`
- Modify: `backend/app/models/prompt.py`
- Modify: `backend/app/models/schema.py`
- Create: `backend/app/models/mixins/shareable.py` or extend `backend/app/models/base.py` with a `ShareableMixin`
- Modify: `backend/app/schemas/evaluator.py`
- Modify: `backend/app/schemas/setting.py`
- Modify: `backend/app/schemas/prompt.py`
- Modify: `backend/app/schemas/schema.py`
- Create: `backend/app/schemas/app_config.py`
- Create: `backend/app/schemas/rule_catalog.py`
- Modify: `backend/app/routes/apps.py`
- Modify: `backend/app/routes/evaluators.py`
- Modify: `backend/app/routes/settings.py`
- Modify: `backend/app/routes/prompts.py`
- Modify: `backend/app/routes/schemas.py`
- Modify: `backend/app/routes/adversarial_config.py`
- Create: `backend/app/routes/rules.py`

### Backend services / jobs / runners / reports

- Modify: `backend/app/services/seed_defaults.py`
- Modify: `backend/app/services/job_worker.py`
- Create: `backend/app/services/evaluators/evaluator_draft_service.py`
- Create: `backend/app/services/evaluators/rules_service.py`
- Modify: `backend/app/services/evaluators/adversarial_config.py`
- Modify: `backend/app/services/evaluators/custom_evaluator_runner.py`
- Modify: `backend/app/services/evaluators/inside_sales_runner.py`
- Modify: `backend/app/services/evaluators/voice_rx_runner.py` only if required for new evaluator metadata reads, not for app-specific flow changes
- Modify: `backend/app/services/reports/custom_evaluations/aggregator.py`

### Frontend types / stores / API clients

- Modify: `src/types/app.types.ts`
- Modify: `src/types/evaluator.types.ts`
- Modify: `src/types/prompt.types.ts`
- Modify: `src/types/schema.types.ts`
- Modify: `src/types/settings.types.ts`
- Modify: `src/types/evalRuns.ts`
- Modify: `src/stores/appStore.ts`
- Modify: `src/stores/evaluatorsStore.ts`
- Modify: `src/stores/promptsStore.ts`
- Modify: `src/stores/schemasStore.ts`
- Modify: `src/stores/llmSettingsStore.ts`
- Modify: `src/services/api/evaluatorsApi.ts`
- Modify: `src/services/api/settingsApi.ts`
- Modify: `src/services/api/promptsApi.ts`
- Modify: `src/services/api/schemasApi.ts`
- Modify: `src/services/api/adversarialConfigApi.ts`
- Create: `src/services/api/appsApi.ts`
- Create: `src/services/api/rulesApi.ts`

### Frontend shared UI / evaluator UX

- Modify: `src/components/ui/VariablePickerPopover.tsx`
- Create: `src/components/ui/VisibilityBadge.tsx`
- Create: `src/components/ui/VisibilityToggle.tsx`
- Create: `src/components/ui/StarToggle.tsx`
- Create: `src/components/ui/RoleBadge.tsx`
- Modify: `src/components/ui/index.ts`
- Create: `src/features/evals/components/EvaluatorsTable.tsx`
- Create: `src/features/evals/components/EvaluatorExpandRow.tsx`
- Create: `src/features/evals/components/CreateEvaluatorWizard.tsx`
- Create: `src/features/evals/components/SchemaTable.tsx`
- Create: `src/features/evals/components/RulePicker.tsx`
- Create: `src/features/evals/components/BuildModeToggle.tsx`
- Retire/replace: `src/features/evals/components/CreateEvaluatorOverlay.tsx`
- Retire/replace: `src/features/evals/components/EvaluatorCard.tsx`
- Retire/replace: `src/features/evals/components/EvaluatorsView.tsx`
- Retire/replace: `src/features/evals/components/EvaluatorRegistryPicker.tsx`
- Retire/replace: `src/features/evals/components/OutputSchemaBuilder.tsx`
- Retire/replace: `src/features/evals/components/InlineSchemaBuilder.tsx`
- Modify: `src/features/evals/pages/AppEvaluatorsPage.tsx`
- Modify: `src/app/pages/ListingPage.tsx`
- Modify: `src/app/pages/kaira/KairaBotTabView.tsx`

### Frontend settings / readers / exports

- Modify: `src/features/settings/components/PromptsTab.tsx`
- Modify: `src/features/settings/components/SchemasTab.tsx`
- Modify: `src/features/settings/components/PromptCreateOverlay.tsx`
- Modify: `src/features/settings/components/SchemaCreateOverlay.tsx`
- Create: `src/features/settings/components/OwnershipBanner.tsx`
- Create: `src/features/settings/components/VersionLibraryActions.tsx`
- Modify: `src/features/evalRuns/components/OutputFieldRenderer.tsx`
- Modify: `src/features/evalRuns/components/EvaluatorPreviewOverlay.tsx`
- Modify: `src/features/evalRuns/components/threadReview/CustomEvalsTab.tsx`
- Modify: `src/features/evalRuns/components/report/customEval/EvaluatorCard.tsx`
- Modify: `src/services/export/resolvers/voiceRxResolver.ts`
- Modify: `src/services/export/exporters/csvExporter.ts` if field visibility assumptions leak there

### Tests

- Create/modify: `backend/tests/test_apps_routes.py`
- Create/modify: `backend/tests/test_evaluators_routes.py`
- Create/modify: `backend/tests/test_settings_routes.py`
- Create/modify: `backend/tests/test_prompts_routes.py`
- Create/modify: `backend/tests/test_schemas_routes.py`
- Create/modify: `backend/tests/test_adversarial_config_routes.py`
- Create/modify: `backend/tests/test_rule_catalog_routes.py`
- Create/modify: `backend/tests/test_custom_evaluation_aggregator.py`
- Create/modify: `src/features/evals/components/__tests__/CreateEvaluatorWizard.test.tsx`
- Create/modify: `src/features/evals/components/__tests__/EvaluatorsTable.test.tsx`
- Create/modify: `src/features/settings/components/__tests__/PromptsTab.test.tsx`
- Create/modify: `src/features/settings/components/__tests__/SchemasTab.test.tsx`
- Create/modify: `src/features/evalRuns/components/__tests__/OutputFieldRenderer.test.tsx`

---

## Phase 1: Backend Data Contracts and Access Primitives

**Objective:** Land the shared ownership model, app config column, and reusable access helper without switching frontend behavior yet.

**Primary files:**
- Modify: `backend/app/models/app.py`
- Modify: `backend/app/models/evaluator.py`
- Modify: `backend/app/models/setting.py`
- Modify: `backend/app/models/prompt.py`
- Modify: `backend/app/models/schema.py`
- Create: `backend/app/models/mixins/shareable.py`
- Create: `backend/app/schemas/app_config.py`
- Modify: `backend/app/schemas/evaluator.py`
- Modify: `backend/app/schemas/setting.py`
- Modify: `backend/app/schemas/prompt.py`
- Modify: `backend/app/schemas/schema.py`
- Create: `backend/app/services/access_control.py`

**Implementation scheme:**
- Add `config` JSONB to `App`.
- Add `visibility`, `shared_by`, `shared_at`, and `forked_from` where required by the spec.
- Add `branch_key` to `Prompt` and `Schema`.
- Replace evaluator legacy sharing flags with the new model.
- Create a reusable `can_access(user, asset, action)` helper with tests covering private, app-shared, and system-seeded cases.
- Keep system defaults modeled as `tenant_id == SYSTEM_TENANT_ID`, `user_id == SYSTEM_USER_ID`, `visibility == 'app'`.

**Checklist:**
- [ ] Add/extend `ShareableMixin` and apply it only to the spec-approved asset families.
- [ ] Update SQLAlchemy models and Pydantic response/create/update schemas to expose new fields with camelCase.
- [ ] Remove evaluator schema fields that encode legacy semantics: `isGlobal`, `isBuiltIn`, `showInHeader`.
- [ ] Add `branch_key` and version uniqueness support to prompt/schema models.
- [ ] Add access-control unit tests for owner/private, app-shared reader, system-seeded reader, and immutable system-row edit denial.
- [ ] Update any seed/model comments so future edits do not reintroduce the legacy sharing model.

**Verification:**
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests/test_evaluators_routes.py backend/tests/test_settings_routes.py backend/tests/test_prompts_routes.py backend/tests/test_schemas_routes.py -v`
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests/test_apps_routes.py backend/tests/test_rule_catalog_routes.py -v`

**Exit gate:**
- Backend model layer compiles, route schemas serialize the new fields cleanly, and no route behavior changes are visible to the frontend yet.

---

## Phase 2: Shared Settings, App Config, and Rules Service

**Objective:** Make app capabilities DB-driven and give rules/contracts a proper backend source without embedding them in `apps.config`.

**Primary files:**
- Modify: `backend/app/routes/apps.py`
- Modify: `backend/app/routes/settings.py`
- Modify: `backend/app/routes/adversarial_config.py`
- Create: `backend/app/routes/rules.py`
- Create: `backend/app/schemas/rule_catalog.py`
- Modify: `backend/app/services/evaluators/adversarial_config.py`
- Create: `backend/app/services/evaluators/rules_service.py`
- Modify: `backend/app/services/seed_defaults.py`
- Modify: `backend/app/models/app.py`
- Modify: `backend/app/models/setting.py`

**Implementation scheme:**
- Extend `/api/apps` and add `/api/apps/{slug}/config`.
- Rework `GET /api/settings` to support resolved reads by default and `includeAll=true` for management views.
- Keep `adversarial-config` as a dedicated product route, but back it with the new shared-settings resolution rules.
- Add a generic rules route pair (`GET /api/rules`, `PUT /api/rules`) that stores the published catalog in app-scoped shared settings using `key='rule-catalog'`.

**Checklist:**
- [ ] Define the app config payload schema exactly as specified.
- [ ] Seed configs for `voice-rx`, `kaira-bot`, and `inside-sales` into the `apps` table.
- [ ] Implement settings resolution: private -> app-shared -> system default.
- [ ] Update adversarial-config service functions to read/write the shared settings row rather than user-private settings.
- [ ] Implement rules service load/save helpers that read/write `rule-catalog` from the settings table.
- [ ] Add route tests proving a member with app access can read shared/system settings, while only `settings:edit` can write shared contracts/catalogs.

**Verification:**
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests/test_apps_routes.py backend/tests/test_settings_routes.py backend/tests/test_adversarial_config_routes.py backend/tests/test_rule_catalog_routes.py -v`

**Exit gate:**
- App config and shared settings are fully DB-backed, rules are externally publishable without code changes, and no UI yet depends on hardcoded app capabilities.

---

## Phase 3: Prompt/Schema Branch Model and Versioned Library APIs

**Objective:** Make prompts and schemas real shareable libraries with deterministic branching and latest-version listing.

**Primary files:**
- Modify: `backend/app/models/prompt.py`
- Modify: `backend/app/models/schema.py`
- Modify: `backend/app/routes/prompts.py`
- Modify: `backend/app/routes/schemas.py`
- Modify: `backend/app/schemas/prompt.py`
- Modify: `backend/app/schemas/schema.py`
- Modify: `src/services/api/promptsApi.ts`
- Modify: `src/services/api/schemasApi.ts`
- Modify: `src/stores/promptsStore.ts`
- Modify: `src/stores/schemasStore.ts`

**Implementation scheme:**
- Persist `branch_key` and version rows.
- Default list endpoints to latest-per-branch and add an opt-in full-history mode.
- Support `PATCH /visibility` and `POST /fork` for prompts and schemas without mutating system defaults or silently changing active selections.

**Checklist:**
- [ ] Rework prompt/schema version increment logic to scope by `branch_key`, not only `prompt_type`.
- [ ] Add fork endpoints that create a new private branch with `version = 1`.
- [ ] Add visibility patch endpoints that operate on the latest row only.
- [ ] Preserve `is_default` only for system-seeded rows.
- [ ] Keep active prompt/schema IDs in private `llm-settings` and do not auto-switch them when a shared branch gets a new version.
- [ ] Add backend tests for latest-per-branch listing, version history expansion, fork semantics, and visibility patch semantics.
- [ ] Update frontend API clients/stores to understand `branchKey`, `visibility`, `ownerName`, and version-history fetches.

**Verification:**
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests/test_prompts_routes.py backend/tests/test_schemas_routes.py -v`
- Run: `npm run lint`

**Exit gate:**
- Prompt/schema APIs expose the exact versioned-library contract the spec describes, and frontend stores can consume them without legacy assumptions.

---

## Phase 4: Evaluator API Harmonization and Output-Schema v2 Backend Cutover

**Objective:** Finish backend evaluator contracts, add the draft job, and update all backend readers away from `displayMode`.

**Primary files:**
- Modify: `backend/app/routes/evaluators.py`
- Modify: `backend/app/schemas/evaluator.py`
- Modify: `backend/app/services/job_worker.py`
- Create: `backend/app/services/evaluators/evaluator_draft_service.py`
- Modify: `backend/app/services/evaluators/custom_evaluator_runner.py`
- Modify: `backend/app/services/reports/custom_evaluations/aggregator.py`
- Modify: `backend/app/services/seed_defaults.py`
- Modify: `backend/app/routes/reports.py` only if payload assumptions break
- Modify: `src/types/evaluator.types.ts`
- Modify: `src/types/evalRuns.ts`

**Implementation scheme:**
- Replace evaluator list/get/create/update/delete semantics with visibility-aware access control and owner metadata.
- Add visibility patch and fork endpoints.
- Add `generate-evaluator-draft` as a job-worker handler using existing LLM provider abstractions and private `llm-settings`.
- Update backend report/running/seed consumers to use `role` + `isMainMetric`.
- Do not switch frontend writers until every backend reader is v2-safe.

**Checklist:**
- [ ] Remove legacy evaluator route operations for `/global` and `/built-in`.
- [ ] Add list filtering for `All`, `Shared`, and `Mine` via visibility-aware query params.
- [ ] Add `ownerId` / `ownerName` to evaluator list responses.
- [ ] Implement evaluator fork and visibility patch endpoints.
- [ ] Implement `generate-evaluator-draft` job with stable error shapes and no direct provider SDK calls.
- [ ] Update evaluator runner/report aggregator logic to ignore `reasoning` fields and locate the main metric through `isMainMetric`.
- [ ] Convert seeded evaluator payloads in `seed_defaults.py` from `displayMode` to `role` semantics.
- [ ] Add tests for visibility-aware evaluator listing and role-based aggregator behavior.

**Verification:**
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests/test_evaluators_routes.py backend/tests/test_custom_evaluation_aggregator.py -v`
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests -k "evaluator or aggregator or rules" -v`

**Exit gate:**
- No backend reader of custom evaluator fields still depends on `displayMode`.

---

## Phase 5: Frontend App Config and Data-Layer Reshaping

**Objective:** Make the frontend capable of reading app config and the new asset contracts before replacing the UI.

**Primary files:**
- Modify: `src/stores/appStore.ts`
- Create: `src/services/api/appsApi.ts`
- Create: `src/services/api/rulesApi.ts`
- Modify: `src/services/api/evaluatorsApi.ts`
- Modify: `src/services/api/settingsApi.ts`
- Modify: `src/services/api/promptsApi.ts`
- Modify: `src/services/api/schemasApi.ts`
- Modify: `src/services/api/adversarialConfigApi.ts`
- Modify: `src/types/app.types.ts`
- Modify: `src/types/evaluator.types.ts`
- Modify: `src/types/prompt.types.ts`
- Modify: `src/types/schema.types.ts`
- Modify: `src/types/settings.types.ts`
- Modify: `src/hooks/useCurrentAppData.ts` and any related hook files if app config needs a dedicated hook

**Implementation scheme:**
- Expand app store to cache app config by slug while keeping current app selection.
- Replace evaluator API types that still expose `isGlobal` / `isBuiltIn` / `showInHeader`.
- Add API wrappers for rules, new prompt/schema version endpoints, and visibility/fork actions.
- Keep adapters explicit and centralized at the API boundary; do not let components hand-roll response shaping.

**Checklist:**
- [ ] Add a `useAppConfig`-style selector/hook backed by `appStore`.
- [ ] Update evaluator/prompt/schema/settings client adapters to parse new fields and dates.
- [ ] Remove hardcoded "registry" assumptions from data stores and replace them with visibility-aware lists.
- [ ] Add helpers for `All` / `Shared` / `Mine` filtering in the store or repository layer, not duplicated in components.
- [ ] Update the adversarial-config API wrapper to the shared-read/shared-write model while preserving its dedicated route surface.

**Verification:**
- Run: `npm run lint`
- Run: `npx tsc -b`

**Exit gate:**
- Frontend data access is ready for the new UX without any shared component still depending on app-name branches for capabilities.

---

## Phase 6: Evaluator UX Replacement

**Objective:** Replace card-based evaluator management with the shared table/wizard flow defined by the spec.

**Primary files:**
- Create: `src/components/ui/VisibilityBadge.tsx`
- Create: `src/components/ui/VisibilityToggle.tsx`
- Create: `src/components/ui/StarToggle.tsx`
- Create: `src/components/ui/RoleBadge.tsx`
- Modify: `src/components/ui/VariablePickerPopover.tsx`
- Create: `src/features/evals/components/EvaluatorsTable.tsx`
- Create: `src/features/evals/components/EvaluatorExpandRow.tsx`
- Create: `src/features/evals/components/CreateEvaluatorWizard.tsx`
- Create: `src/features/evals/components/SchemaTable.tsx`
- Create: `src/features/evals/components/RulePicker.tsx`
- Create: `src/features/evals/components/BuildModeToggle.tsx`
- Modify: `src/features/evals/pages/AppEvaluatorsPage.tsx`
- Modify: `src/app/pages/ListingPage.tsx`
- Modify: `src/app/pages/kaira/KairaBotTabView.tsx`
- Retire/replace: `src/features/evals/components/CreateEvaluatorOverlay.tsx`
- Retire/replace: `src/features/evals/components/EvaluatorCard.tsx`
- Retire/replace: `src/features/evals/components/EvaluatorsView.tsx`
- Retire/replace: `src/features/evals/components/EvaluatorRegistryPicker.tsx`
- Retire/replace: `src/features/evals/components/OutputSchemaBuilder.tsx`
- Retire/replace: `src/features/evals/components/InlineSchemaBuilder.tsx`
- Preserve integration with: `src/features/insideSales/components/RubricBuilder.tsx`, `src/features/evals/components/ArrayItemConfigModal.tsx`

**Implementation scheme:**
- Read all capability differences from app config.
- Use a single table for all apps.
- Use a single wizard for create/edit with build-mode and rule-step toggles from config.
- Route draft generation through `submitAndPollJob()`.
- Keep static + dynamic variable picking merged in `VariablePickerPopover`.

**Checklist:**
- [ ] Build generic UI primitives first and export them through `src/components/ui/index.ts`.
- [ ] Refactor variable picker to accept config-provided static variables and backend-provided dynamic sources.
- [ ] Build `SchemaTable` around `role` + `isMainMetric`; remove any `displayMode` radio logic.
- [ ] Build `CreateEvaluatorWizard` with prompt, schema, and conditional rules steps.
- [ ] Call `submitAndPollJob('generate-evaluator-draft', ...)` from the wizard; no component polling loops.
- [ ] Build `EvaluatorsTable` with `All` / `Shared` / `Mine`, owner/visibility columns, row expansion, and ownership-aware action menus.
- [ ] Replace the legacy evaluator entry points in listing- and app-level pages with the new shared components.
- [ ] Update `RubricBuilder` integration to emit v2 output-schema fields (`role`, `isMainMetric`) without reintroducing `displayMode`.

**Verification:**
- Run: `npm run lint`
- Run: `npx tsc -b`
- Add/Run: frontend component tests for table actions, build-mode toggling, and schema-table main-metric behavior

**Exit gate:**
- No user-facing evaluator management path still uses the old card grid, registry picker, or `displayMode` builder.

---

## Phase 7: Prompt/Schema/Adversarial Shared-Library UX

**Objective:** Make the settings area reflect the new sharing/versioning model cleanly and predictably.

**Primary files:**
- Modify: `src/features/settings/components/PromptsTab.tsx`
- Modify: `src/features/settings/components/SchemasTab.tsx`
- Modify: `src/features/settings/components/PromptCreateOverlay.tsx`
- Modify: `src/features/settings/components/SchemaCreateOverlay.tsx`
- Create: `src/features/settings/components/OwnershipBanner.tsx`
- Create: `src/features/settings/components/VersionLibraryActions.tsx`
- Modify: `src/services/api/adversarialConfigApi.ts`

**Implementation scheme:**
- Preserve the existing grouping by `prompt_type` and `source_type`.
- Add visibility, owner, version, share/fork actions, and history entry points.
- Make adversarial-config read/write semantics match the shared-settings model.
- Keep active prompt/schema selection private and explicit.

**Checklist:**
- [ ] Surface latest-per-branch prompt/schema rows by default, with version history affordances when requested.
- [ ] Add `Save as Mine`, `Save to Shared Library`, `Share with app`, `Make private`, and `Fork` actions according to the asset type and ownership.
- [ ] Show ownership/visibility metadata without exposing sharing controls for `llm-settings`.
- [ ] Add `OwnershipBanner` to settings-backed shared contracts.
- [ ] Update adversarial config UI/API usage so members can read shared config with app access while only `settings:edit` users can publish changes.

**Verification:**
- Run: `npm run lint`
- Run: `npx tsc -b`
- Add/Run: component tests for prompt/schema visibility actions and adversarial-config read/write gating

**Exit gate:**
- Settings UX matches the spec’s asset model and does not create any surprise implicit sharing behavior.

---

## Phase 8: Reader Cleanup, Guides, Seeds, and Full Verification

**Objective:** Remove legacy assumptions, refresh seeds/docs, and verify the rollout end to end.

**Primary files:**
- Modify: `src/features/evalRuns/components/OutputFieldRenderer.tsx`
- Modify: `src/features/evalRuns/components/EvaluatorPreviewOverlay.tsx`
- Modify: `src/features/evalRuns/components/threadReview/CustomEvalsTab.tsx`
- Modify: `src/features/evalRuns/components/report/customEval/EvaluatorCard.tsx`
- Modify: `src/services/export/resolvers/voiceRxResolver.ts`
- Modify: `backend/app/services/seed_defaults.py`
- Modify: guide/demo/reference files under `src/features/guide/**` that encode legacy evaluator metadata
- Modify: docs under `docs/PROJECT 101.md`, `docs/SETUP.md`, or other touched docs if route or seed behavior is documented there

**Implementation scheme:**
- Remove remaining `displayMode`, `isGlobal`, `isBuiltIn`, and `showInHeader` assumptions from runtime readers, guide data, and preview surfaces.
- Re-seed built-in assets using the new contracts.
- Verify both backend and frontend from the top-level commands in `AGENTS.md`.

**Checklist:**
- [ ] Update all run-detail/report/export readers to honor `role` and `isMainMetric`.
- [ ] Update preview overlays and guide/demo data so they reflect the new evaluator schema semantics.
- [ ] Refresh seed data and system rows with `visibility='app'` and `branch_key` where needed.
- [ ] Run typecheck, lint, and targeted backend tests, then run the highest-signal end-to-end manual sanity pass:
  - app list loads config
  - member sees shared/system assets
  - member cannot see another user's private asset
  - member can fork shared/system assets
  - admin can publish shared contracts/catalogs
  - prompt/schema active selection stays private
  - wizard draft generation works and degrades cleanly when credentials are missing

**Verification:**
- Run: `pyenv activate venv-python-ai-evals-arize && pytest backend/tests -v`
- Run: `npm run lint`
- Run: `npx tsc -b`
- Run: if feasible, app smoke test via `docker compose up --build`

**Exit gate:**
- Legacy sharing/display concepts are fully retired in the touched surfaces, and the implementation matches the spec without hidden fallback behavior.

---

## Dependency Notes

- Phase 1 must finish before any route/UI work that consumes `visibility`, `branch_key`, or app config.
- Phase 2 must finish before wizard rule-picker work or app-config-driven capability toggles.
- Phase 4 backend reader cutover must finish before Phase 6 switches evaluator writers to v2 schema semantics.
- Phase 5 is the frontend prerequisite for both Phase 6 and Phase 7.
- Phase 8 is mandatory; do not skip guide/reader cleanup or stale legacy assumptions will survive in reporting and preview surfaces.

## Spec Coverage Check

- Evaluator UI unification: covered by Phases 5-6.
- Asset ownership model and RBAC/UX: covered by Phases 1-2 and Phase 7.
- App config schema and DB-driven capability checks: covered by Phases 2 and 5.
- Prompt/schema branch model: covered by Phase 3.
- Rules as DB-backed runtime catalog, not `apps.config`: covered by Phase 2.
- Output schema v2 atomic cutover: covered by Phases 4 and 8.
- Shared/system/private onboarding behavior from the addendum: covered by Phases 2, 6, 7, and 8 verification.

## Non-Goals

- No change to app-specific evaluation pipelines such as Voice Rx transcription ordering or Inside Sales domain logic beyond consuming new evaluator metadata safely.
- No shared LLM credentials.
- No new permission strings in v1.
- No extra compatibility layer for `displayMode` once all readers are cut over.
