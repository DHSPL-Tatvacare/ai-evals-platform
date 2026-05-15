# Phase 15 — Orchestration RBAC + Visibility

> **Status:** implemented (code complete, doc tail open) — verified 2026-05-08
> **Branch base:** `feat/phase-15-orchestration-rbac` from `main` (merged)
> **Depends on:** none. Self-contained backend phase + minor FE wiring.
> **Lands before:** Platform Phase 15 Wave 7 (orchestration TanStack Query migration) and Platform Phase 16 (OpenAPI codegen). Reason: query keys + response models change shape here; doing TQ/codegen first would force a redo.

## Why this phase exists

Orchestration entities (workflows, connections, datasets) today have:
- **Zero permission gate** beyond app access. Anyone with `inside-sales` in `app_access` can create, edit, publish, run, and delete every workflow and connection in the tenant.
- **No per-row visibility.** No notion of "my draft" vs "team-shared". Every user sees every row their app permits.

This is fine for two-person tenants. It does not survive a tenant where Authors build campaigns, Operators run them, and Viewers watch dashboards.

The platform already has the right primitives — `permission_catalog` for role-based perms, `ShareableMixin` + `Visibility` for per-row visibility, `access_control.can_access` for ownership rules. Evaluators and EvalTemplates use them. This phase brings orchestration onto the same model.

---

## The model in plain terms

**One permission, set on a role:**
- `orchestration:manage` — ON ⇒ user can create/edit/publish/run/share/delete the orchestration entities they own. OFF ⇒ read-only.

**One canonical owner concept:**
- Today orchestration rows use `created_by`; the rest of the shareable-asset stack mostly thinks in terms of `user_id`.
- For this phase, treat those as the **same ownership concept**. Step 1 is to rationalize the implementation so the platform has one structurally consistent owner story again — either by schema, by shared access-control code, or by both.

**Two visibility states per row:**
- `private` (default) — only the creator sees it.
- `shared` — anyone in the same tenant with the matching `app_access` sees it.

**Edit/Delete/Share rule** — owner only, even with the perm. The perm gates *whether you can take write actions at all*; ownership gates *which rows you can act on*. Owner role bypasses both.

**Reads** — gated by `app_access` + visibility. No read permission needed.

**Sidebar** — unchanged. Anyone with the app sees Campaigns + Connections in the nav. Read-only users land on a list with all action buttons hidden.

---

## Architecture posture (the keystones)

1. **One permission for the whole orchestration surface.** `orchestration:manage`. Covers workflows, connections, datasets, triggers, runs (Run Now / cancel / override), action templates, consent. No per-asset-class split. No author/operator split. If product later needs a separate "run but don't author" tier, that's a follow-up — don't speculate now.
2. **Normalize ownership semantics before layering visibility on top.** `created_by` and `user_id` are supposed to represent the same owner concept. This phase makes that explicit. Do not bolt visibility onto orchestration while leaving ownership ambiguous.
3. **Mirror the Evaluator visibility pattern after ownership is rationalized.** Same `ShareableMixin` (`visibility`, `shared_by`, `shared_at`). Same `?filter=all|private|shared` list-query convention. Same `access_control.can_access` / readable-scope mental model. Zero new mental model after the ownership cleanup.
4. **Workflow versions, triggers, runs, recipient states inherit visibility from their parent workflow.** Don't add visibility columns on child rows. Read-gate them by joining/loading the workflow and checking parent visibility.
5. **System workflows stay shared.** `mql-concierge-default`, `dm2-adherence-watch` are seeded with `visibility=shared`, `tenant_id=SYSTEM_TENANT_ID`. The existing clone-then-own flow is unchanged — cloning produces a tenant-owned row with `visibility=private`.
6. **Backfill existing rows to `shared`.** Pragmatic — tenants today already see each other's workflows; flipping all to `private` would break running campaigns. Going forward, new rows default to `private`.
7. **Connection secrets stay redacted on GET regardless of visibility.** `visibility=shared` reveals the connection's *existence and non-secret config*, not credentials. The strip-secrets-on-GET invariant in CLAUDE.md is unchanged.
8. **Webhook public routes are out of scope.** `/api/orchestration/webhooks/*` is unauthenticated by design (provider callbacks resolve by `webhook_token`); no perm or visibility check applies. Worker-side resume polling and `run-workflow` job runner are system actors — they bypass user auth entirely.
9. **FE permission staleness is pre-existing, not this phase's problem.** `authStore.user.permissions` loads at login and lives until reload. A tenant admin who flips a role mid-session: target user must reload. Same gap exists for `cost:view`, `schedule:manage`. One-line note in the plan, no fix here.

---

## Hard constraints

1. **One permission, one shape.** Adding more perms (separate publish, separate run, per-asset-class splits) is rejected for this phase. Re-open in a follow-up if real demand surfaces.
2. **No new ACL tables.** Visibility is a column, not a join.
3. **Reads stay readable for everyone with app access.** Don't add read-permission gates that would hide the Campaigns/Connections sidebar entry. The viewer experience must be: see the list, see no buttons.
4. **Owner role keeps bypassing everything.** Both the perm check and the ownership check. Tenant cleanup escape hatch.
5. **Sharing toggles via existing PATCH endpoints, not a new `/share` route.** Patch the row with `{"visibility": "shared"}`. Mirrors `evaluators` PATCH behavior.
6. **System workflows are not user-editable.** `tenant_id=SYSTEM_TENANT_ID` rows are read-only for regular users, regardless of perm. Editing them would mean editing every tenant's clones.
7. **Migration is one Alembic revision.** Backfill is part of the same migration. Reversible (drop columns) for safety.
8. **Ownership must be canonical by the end of the phase.** If orchestration stays on `created_by`, shared access-control helpers must explicitly understand that. If orchestration gains `user_id`, migration/backfill must make it authoritative. No half-state where both exist but callers guess.
9. **No FE changes required for the perm to be live.** Backend gates first; FE enhancements (filter pill, badges, button-hiding) follow but don't block backend ship. If FE doesn't pick up the perm, write actions return 403 and the existing `decodeApiError` path renders the message.

---

## What this phase deliberately does not do

- No author/operator/viewer split inside `orchestration:manage`. Single perm.
- No row-level ACLs, no Notion-style sharing, no "share with user X".
- No cross-app visibility. A workflow in `inside-sales` is invisible to a `voice-rx`-only user — that's still controlled by `app_access`.
- No editable system workflows. System rows remain clone-to-own.
- No webhook auth changes. Public webhook endpoints stay public.
- No FE permission re-fetching. Staleness is a known gap, not this phase's scope.
- No edits to the `run-workflow` / `resume-waiting-cohorts` job runners. They run as system, not as the originating user.

---

## File structure

### Backend — modified

- `backend/app/auth/permission_catalog.py` — add `orchestration` group with one entry.
- `backend/app/models/orchestration.py` — `Workflow`, `CohortDataset` mix in `ShareableMixin`; ownership semantics (`created_by` vs `user_id`) are rationalized here or in shared ownership helpers.
- `backend/app/models/provider_connection.py` — `ProviderConnection` mixes in `ShareableMixin`; ownership semantics are rationalized here or in shared ownership helpers.
- `backend/app/services/access_control.py` — update shared-access helpers so orchestration rows participate structurally in the same owner/visibility model as other shareable assets.
- `backend/app/services/asset_policy.py` — add orchestration asset-family aliases/policies explicitly; don't leave this implicit.
- `backend/app/schemas/orchestration*.py` — response models gain `visibility`, `sharedBy`, `sharedAt`. PATCH request models accept optional `visibility`.
- `backend/app/routes/orchestration.py` — add `require_permission('orchestration:manage')` to write routes; add `?filter=` to list routes.
- `backend/app/routes/orchestration_connections.py` — same treatment.
- `backend/app/routes/orchestration_datasets.py` — same treatment, plus a new `PATCH /datasets/{id}` (currently no PATCH exists; needed for visibility toggle).
- `backend/app/seeds/data/orchestration.workflows.json` (or wherever system workflows are seeded) — set `visibility: "shared"`.
- `CLAUDE.md` — invariants list updated cumulatively at the end.

### Backend — new

- `backend/alembic/versions/00XX_orchestration_visibility.py` — migration: add columns + backfill.

### Frontend — modified

- `src/features/orchestration/types.ts` — extend workflow-side types with `visibility`, `sharedBy`, `sharedAt`.
- `src/services/api/orchestrationConnections.ts` — extend `Connection` response shape with `visibility`, `sharedBy`, `sharedAt`.
- `src/services/api/orchestrationDatasets.ts` — extend dataset response shapes with `visibility`, `sharedBy`, `sharedAt`.
- `src/features/orchestration/components/WorkflowListPage.tsx` — Create button gated by `usePermission('orchestration:manage')`; visibility filter pill; row badge.
- `src/features/orchestration/components/WorkflowBuilderPage.tsx` + `WorkflowHeaderBar.tsx` — Save / Publish / Run Now / Delete / Share buttons gated by perm; Share button additionally gated by ownership.
- Run drill-in surfaces (`RunInspectorOverlay` / recipients-actions controls, and legacy `RunDetailPage` if still reachable) — Cancel / Override Recipient buttons gated by perm.
- `src/features/orchestration/components/connections/ConnectionsPage.tsx` + `ConnectionForm.tsx` — Create / Save / Delete / Test / Rotate Webhook / Share buttons gated.
- `src/features/orchestration/components/datasets/DatasetsPage.tsx` + `datasets/DatasetDetail.tsx` — Create / Delete / Upload / Share buttons gated; filter pill; badge.
- `src/features/orchestration/components/connections/ConnectionPicker.tsx` and `components/datasets/DatasetSourcePicker.tsx` — dropdowns list own + shared only (server-filtered).
- `src/components/ui/VisibilityToggle.tsx` — reuse if it already fits; only extract a new orchestration wrapper if the existing component shape is wrong.
- `src/components/layout/Sidebar.tsx` — **no change** (sidebar entry stays gated only by app_access).

### Frontend — new

- `src/features/orchestration/utils/canEditOrchestrationRow.ts` — small helper: `(user, row) => userHasPermission(user, 'orchestration:manage') && row.createdBy === user.id`. Used by builder/edit modals.

---

## Permission surface — exhaustive enumeration

Every orchestration endpoint, classified. Read = no perm needed (visibility-driven). Write = `require_permission('orchestration:manage')`. System = unauthenticated/system-actor, no change.

### Workflows (`backend/app/routes/orchestration.py`)

| Method | Path | Class | Notes |
|---|---|---|---|
| POST | `/workflows` | **Write** | Creator becomes owner; default `visibility=private` |
| GET | `/workflows` | Read | Returns own + shared in app; honors `?filter=` |
| GET | `/system-workflows` | Read | System tenant rows; always visible to anyone with app access |
| GET | `/workflows/{id}` | Read | Visibility check |
| PATCH | `/workflows/{id}` | **Write** | Owner-only; visibility togglable here |
| DELETE | `/workflows/{id}` (archive) | **Write** | Owner-only |
| POST | `/workflows/clone` | **Write** | Anyone with perm; clone owner = caller |
| POST | `/workflows/{id}/versions` | **Write** | Owner-only |
| GET | `/workflows/{id}/versions` | Read | Inherits parent visibility |
| GET | `/workflows/{id}/versions/{vid}` | Read | Inherits parent visibility |
| POST | `/workflows/{id}/versions/{vid}/publish` | **Write** | Owner-only |
| POST | `/workflows/{id}/triggers` | **Write** | Owner-only on parent workflow |
| GET | `/workflows/{id}/triggers` | Read | Inherits parent visibility |
| PATCH | `/triggers/{id}` | **Write** | Owner-only on parent workflow |
| DELETE | `/triggers/{id}` | **Write** | Owner-only on parent workflow |
| POST | `/runs` (manual fire / Run Now) | **Write** | Owner-only on parent workflow |
| GET | `/runs` | Read | Filtered by parent workflow visibility |
| GET | `/actions` | Read | Cross-workflow action log; must filter to runs whose parent workflow is readable |
| GET | `/runs/{id}` | Read | Inherits parent visibility |
| GET | `/runs/{id}/overlay` | Read | Inherits parent visibility |
| GET | `/runs/{id}/recipients` | Read | Inherits parent visibility |
| GET | `/runs/{id}/actions` | Read | Inherits parent visibility |
| GET | `/runs/{id}/actions/{action_id}` | Read | Inherits parent visibility |
| POST | `/runs/{id}/cancel` | **Write** | Owner-only on parent workflow |
| POST | `/runs/{id}/recipients/{rid}/override` | **Write** | Owner-only on parent workflow |
| GET | `/action_templates` | Read | Tenant-shared library; no per-row visibility (treat as always-shared) |
| POST | `/action_templates` | **Write** | Tenant-wide; no row owner gate |
| GET | `/consent/{recipient_id}` | Read | Tenant-scoped only; no per-row visibility |
| POST | `/consent` | **Write** | Tenant-wide; no row owner gate |
| GET | `/node_types` | Read | Static catalog; no perm or visibility |
| GET | `/source_catalog` | Read | Static catalog; no perm or visibility |

### Connections (`backend/app/routes/orchestration_connections.py`)

| Method | Path | Class | Notes |
|---|---|---|---|
| GET | `/connections/schema` | Read | Static provider schema; no gate |
| POST | `/connections` | **Write** | Creator = owner; default `visibility=private` |
| GET | `/connections` | Read | Own + shared; honors `?filter=` |
| GET | `/connections/{id}` | Read | Visibility check; secrets always stripped |
| PATCH | `/connections/{id}` | **Write** | Owner-only; visibility togglable here |
| DELETE | `/connections/{id}` | **Write** | Owner-only |
| POST | `/connections/{id}/test` | **Write** | Owner-only (calls upstream API with creds) |
| POST | `/connections/{id}/rotate-token` | **Write** | Owner-only |
| GET | `/connections/{id}/agent-variables` | Read | Visibility check |
| GET | `/connections/{id}/agents` | Read | Visibility check |
| GET | `/connections/{id}/templates` | Read | Visibility check |

### Datasets (`backend/app/routes/orchestration_datasets.py`)

| Method | Path | Class | Notes |
|---|---|---|---|
| POST | `/datasets` | **Write** | Creator = owner |
| GET | `/datasets` | Read | Own + shared |
| GET | `/datasets/{id}` | Read | Visibility check |
| **PATCH** | **`/datasets/{id}`** | **Write** | **NEW endpoint** — needed for visibility toggle |
| DELETE | `/datasets/{id}` | **Write** | Owner-only |
| POST | `/datasets/{id}/versions` (upload) | **Write** | Owner-only on parent dataset |
| GET | `/datasets/{id}/versions/{vid}` | Read | Inherits parent visibility |
| DELETE | `/datasets/{id}/versions/{vid}` | **Write** | Owner-only on parent dataset |

### Workers / system actors (no change)

- `app/services/job_worker.py` running `run-workflow` and `resume-waiting-cohorts` — these execute as the system, not the user who triggered them. They bypass `AuthContext` and continue to do so.
- `backend/app/routes/orchestration_webhooks.py` (`/api/orchestration/webhooks/*`) — public, unauthenticated, resolved by `webhook_token`. Untouched.

### Frontend permission surface — exhaustive

Every place the FE shows a write action today, must guard with `usePermission('orchestration:manage')` AND, where applicable, ownership.

| Surface | Action | Guard |
|---|---|---|
| Campaigns list page | "+ New Campaign" | perm |
| Campaigns list page | "Clone from system template" | perm |
| Campaign builder header | Save | perm + owner |
| Campaign builder header | Publish | perm + owner |
| Campaign builder header | Run Now | perm + owner |
| Campaign builder header | Delete (archive) | perm + owner |
| Campaign builder header | Share toggle | perm + owner |
| Campaign builder canvas | Edit any node config | perm + owner (read-only render otherwise) |
| Trigger list / cron settings | Add / Edit / Delete trigger | perm + owner of workflow |
| Run detail page | Cancel run | perm + owner of workflow |
| Run detail page | Override recipient | perm + owner of workflow |
| Connections list page | "+ New Connection" | perm |
| Connection edit modal | Save | perm + owner |
| Connection edit modal | Delete | perm + owner |
| Connection edit modal | Test connection | perm + owner |
| Connection edit modal | Rotate webhook token | perm + owner |
| Connection edit modal | Share toggle | perm + owner |
| Datasets list page | "+ New Dataset" | perm |
| Dataset detail | Upload version | perm + owner |
| Dataset detail | Delete dataset / version | perm + owner |
| Dataset detail | Share toggle | perm + owner |
| Workflow builder — connection picker dropdown | List entries | scoped to own + shared (server-filtered) |
| Workflow builder — dataset picker (cohort source) | List entries | scoped to own + shared (server-filtered) |
| Sidebar Campaigns / Connections entries | Visibility | **app_access only — unchanged** |

---

## Step-by-step plan

### Stage A — Backend foundation (~½ day)

- [ ] A-1. Add `orchestration` permission group to `backend/app/auth/permission_catalog.py`:
  ```python
  PermissionGroup(
      id="orchestration",
      label="Orchestration",
      description="Manage campaigns, connections, and cohort datasets.",
      permissions=(
          PermissionCatalogEntry(
              id="orchestration:manage",
              label="Manage orchestration",
              description="Create, edit, publish, run, share, and delete workflows, connections, and datasets the user owns.",
              grantable=True,
              owner_only=False,
          ),
      ),
  )
  ```
  Verify `VALID_PERMISSIONS` recomputes to include the new entry. No other catalog change.

- [ ] A-2. **Rationalize ownership semantics first.** Decide and document the canonical owner field for orchestration rows:
  - If we keep `created_by` as the persisted owner column, shared access-control helpers must explicitly treat it as the orchestration equivalent of `user_id`.
  - If we add `user_id`, the migration must backfill it from `created_by` and code must stop guessing between the two.
  - End state requirement: no route/helper should need to "remember" that orchestration is special.

- [ ] A-3. **Update `asset_policy.py` explicitly.** Add orchestration asset families / aliases (`workflows`, `provider_connections`, `cohort_datasets`) so the shared asset-policy layer knows these rows are shareable. Don't leave this as a maybe.

- [ ] A-4. Confirm `app/services/access_control.py:can_access` and readable-scope helpers are truly polymorphic over the rationalized orchestration owner field. If they assume `user_id`, generalize them now. One-time refactor; document inline.

- [ ] A-5. **Add tests for the perm catalog.** `backend/tests/test_permission_catalog.py` — assert `'orchestration:manage'` is in `VALID_PERMISSIONS`, group serializes, grantable flag is true.

### Stage B — Models + migration (~½ day)

- [ ] B-1. **`Workflow`** in `backend/app/models/orchestration.py`:
  ```python
  class Workflow(Base, ShareableMixin):
      __tablename__ = "workflows"
      __table_args__ = (..., {"schema": "orchestration"})
      ...
  ```
  Plus the ownership rationalization from Stage A: either add the canonical owner column or make the shared ownership helpers understand the existing one. `ShareableMixin`'s `shared_by` FK targets `platform.users.id` — already cross-schema, fine.

- [ ] B-2. **`ProviderConnection`** in `backend/app/models/provider_connection.py` — add `ShareableMixin`.

- [ ] B-3. **`CohortDataset`** in `backend/app/models/orchestration.py` — add `ShareableMixin`.

- [ ] B-4. **Add the indexes needed for the new visibility queries.** Mirror the shareable-asset pattern: owner + app + created/updated ordering, and tenant + app + visibility ordering. Don't ship new gating logic without the supporting indexes.

- [ ] B-5. **WorkflowVersion / WorkflowTrigger / WorkflowRun / WorkflowRunRecipientState** — **do not** add `ShareableMixin`. Visibility inherits from parent workflow. Document inline.

- [ ] B-6. **Alembic migration** `00XX_orchestration_visibility.py`:
  ```python
  # add columns
  op.add_column('workflows', sa.Column('visibility', ...), schema='orchestration')
  op.add_column('workflows', sa.Column('shared_by', ...), schema='orchestration')
  op.add_column('workflows', sa.Column('shared_at', ...), schema='orchestration')
  # FK to platform.users (with ondelete SET NULL)
  op.create_foreign_key(..., source_schema='orchestration', referent_schema='platform', ondelete='SET NULL')
  # repeat for provider_connections, cohort_datasets

  # backfill existing rows
  op.execute("""
    UPDATE orchestration.workflows
       SET visibility = 'shared',
           shared_by  = created_by,
           shared_at  = created_at
     WHERE visibility = 'private'
  """)
  # repeat for connections, datasets

  # leave system workflows on 'shared' (already covered by the above WHERE)
  ```
  If Stage A chose a schema-level owner normalization (`user_id` added, renamed, or backfilled), do that in this same revision.
  Downgrade: `drop_column` for the three columns + FKs. Reversible.

  Schema-qualify every raw SQL statement (CLAUDE.md invariant).

- [ ] B-7. Update `backend/app/seeds/data/orchestration.workflows.json` (or wherever system workflows are seeded) — set `visibility: "shared"` for `mql-concierge-default` and `dm2-adherence-watch`. Verify seed loader picks up the new key.

- [ ] B-8. Run migration end-to-end on a dev DB, verify backfill, verify `Visibility` enum constraint accepts `private` / `shared` only, and verify ownership reads/writes all go through the now-canonical owner concept.

### Stage C — Schemas (~¼ day)

- [ ] C-1. Workflow / Connection / Dataset response models gain three fields:
  ```python
  visibility: Visibility = Visibility.PRIVATE
  shared_by: uuid.UUID | None = None
  shared_at: datetime | None = None
  ```
  All three serialize as camelCase via `CamelORMModel`.

- [ ] C-2. PATCH request models gain optional `visibility`:
  ```python
  class WorkflowUpdateRequest(CamelModel):
      ...
      visibility: Visibility | None = None
  ```
  Same for `ConnectionUpdateRequest`. Add new `DatasetUpdateRequest` (currently no PATCH endpoint exists for datasets).

- [ ] C-3. List query params accept `filter: Literal['all', 'private', 'shared'] = 'all'`. Default `all` matches today's behavior for users who have everything shared.

### Stage D — Routes (~1 day)

The big one. Every write route gets the perm gate. Every list/detail gets visibility-aware loading. Existing `_load_and_gate_workflow` / `_load_and_gate_connection` / `_load_and_gate_dataset` helpers extend to honor visibility, and all readable-scope logic must use the canonicalized owner semantics from Stage A/B.

- [ ] D-1. **Extend gate helpers** (`backend/app/services/orchestration/api/_helpers.py` or wherever `_load_and_gate_*` lives):
  - `_load_and_gate_workflow(db, auth, workflow_id, action='read')` — for `read`: must own OR (tenant match + visibility=shared) OR (system + shared). For `write`: must own AND have perm. System rows: never writable.
  - Same shape for connection, dataset.
  - Owner role bypass stays.

- [ ] D-2. **Workflows routes** — apply per the table above. Specifically:
  - POST/PATCH/DELETE/clone/versions/publish/triggers/runs (POST)/cancel/override → `require_permission('orchestration:manage')` dependency.
  - List: accept `?filter=`. Use the shared readable-scope approach, but only after the owner-field rationalization is complete.
  - Detail / versions / triggers / runs / overlay / recipients / actions / per-action detail → load through extended gate helper.
  - Cross-workflow `GET /actions` must filter by readable parent workflow, not just tenant/app.

- [ ] D-3. **Connections routes** — same.

- [ ] D-4. **Datasets routes** — same. Add `PATCH /datasets/{id}` on the existing dataset resource, backed by `DatasetUpdateRequest` (visibility toggle + name/description edit).

- [ ] D-5. **Action templates + consent** — these are tenant-shared today. Keep as tenant-scoped, gate writes with `orchestration:manage`, no per-row visibility.

- [ ] D-6. **Public webhook routes** — confirm zero changes. Webhook resolution by `webhook_token` is unchanged.

- [ ] D-7. Update `backend/app/services/orchestration/api/clone.py` — clone route creates a new tenant-owned row with `visibility=private`, `shared_by=None`, `shared_at=None`. Caller becomes owner through the canonicalized owner field.

### Stage E — Backend tests (~½ day)

- [ ] E-1. **Permission gate tests** — for each owner-scoped write endpoint, parametrize: (no perm + own) → 403; (perm + own) → 200; (perm + not own) → 403; (perm + system row) → 403; (owner role) → 200. For action templates / consent, test perm-gated tenant-wide behavior separately.
- [ ] E-2. **Visibility filter tests** — list endpoint with `filter=private`, `shared`, `all` returns expected row sets across (own private, own shared, teammate shared, teammate private, system shared).
- [ ] E-3. **Inherited visibility tests** — workflow versions, runs, triggers, recipients, actions, and per-action detail all inherit parent workflow visibility.
- [ ] E-4. **Connection secret stripping** — `visibility=shared` does not leak `config.secret_*` keys on GET.
- [ ] E-5. **Webhook bypass** — POST `/api/orchestration/webhooks/wati/{token}` works with no auth and no perm.
- [ ] E-6. **Worker bypass** — `run-workflow` job execution does not call `ensure_permissions`.
- [ ] E-7. **Ownership normalization tests** — whichever implementation path we choose, prove that `created_by` / `user_id` no longer drift semantically in orchestration reads/writes/gates.

### Stage F — Frontend wiring (~1 day)

- [ ] F-1. Extend the actual orchestration FE data shapes:
  - `src/features/orchestration/types.ts` for workflows
  - `src/services/api/orchestrationConnections.ts` for connections
  - `src/services/api/orchestrationDatasets.ts` for datasets

- [ ] F-2. `src/features/orchestration/utils/canEditOrchestrationRow.ts`:
  ```ts
  export function canEditOrchestrationRow(
    user: User | null | undefined,
    row: { createdBy: string; tenantId: string },
  ): boolean {
    if (!user) return false;
    if (user.isOwner) return true;
    if (!userHasPermission(user, 'orchestration:manage')) return false;
    return row.createdBy === user.id && row.tenantId === user.tenantId;
  }
  ```
  Plus a `useCanEditOrchestrationRow(row)` reactive hook over `authStore`.

- [ ] F-3. **List pages** — `WorkflowListPage`, `ConnectionsPage`, `DatasetsPage`:
  - Hide "+ New" button when `!usePermission('orchestration:manage')`.
  - Add `<FilterPills>` wired to `?filter=all|private|shared` query param. Default `all`.
  - Add a small visibility badge on each row (Private 🔒 / Shared 👥, mirror evaluator visibility chip).

- [ ] F-4. **Builder + edit surfaces** — `WorkflowBuilderPage` / `WorkflowHeaderBar`, connection slide-over backed by `ConnectionForm`, and `DatasetDetail`:
  - Save / Publish / Run Now / Delete / Test / Rotate Webhook / Upload / Share buttons → `useCanEditOrchestrationRow(row)` guard. Disabled with tooltip when read-only.
  - Add a `<VisibilityToggle>` on the row's edit surface (or extract evaluator's component if reusable). PATCH the row on toggle.

- [ ] F-5. **Run surfaces** — `RunInspectorOverlay` / recipient controls (and `RunDetailPage` if still reachable) — Cancel + Override Recipient buttons → guard.

- [ ] F-6. **Connection picker / dataset picker dropdowns inside the builder** — if backend list now scopes to own+shared, FE just consumes; verify the picker renders empty state correctly when a user opens a shared workflow that references a connection or dataset they cannot currently read (display "Not visible to you" placeholder, don't crash).

- [ ] F-7. **Sidebar — verify zero changes.** Read-only viewer with `inside-sales` access still sees Campaigns + Connections in nav.

### Stage G — Documentation (~¼ day)

- [ ] G-1. CLAUDE.md cumulative updates:
  - Add to **Permission registry** line: `orchestration:manage` covers workflows/connections/datasets/triggers/runs/action templates/consent. Owner bypasses; ownership gates which rows.
  - Add to **Invariants**: "Orchestration write actions require `orchestration:manage`. Edit/delete/share are owner-only on top of the perm. Reads gated by app_access + Shareable visibility (private | shared). System workflows are always shared and never user-editable; clone-then-own."
  - Add to **Invariants**: "Workflow versions, triggers, runs, recipient states inherit visibility from their parent workflow — they have no `visibility` column of their own."
  - Add to **Invariants**: "Connection secrets are stripped on GET regardless of visibility — `visibility=shared` reveals existence and non-secret config only."
- [ ] G-2. Update orchestration design-spec.md (`docs/plans/orchestration/design-spec.md`) to reflect the new auth/visibility model.
- [ ] G-3. Note in the plan header that this lands before Phase 15 Wave 7 (TQ migration) and Phase 16 (codegen). Both upcoming phases will pick up the new schema fields automatically.

### Stage H — Acceptance (~¼ day)

- [ ] H-1. `docker compose up --build` clean boot. Migration runs on first start.
- [ ] H-2. Backend tests green.
- [ ] H-3. Browser smoke matrix:
  - **Owner** — full power, every button visible.
  - **Author role with `orchestration:manage` ON** — creates a campaign (visible only to them), shares it, teammate sees it; teammate-Author can't edit it; teammate-Author clones their own copy.
  - **Viewer role with perm OFF** — sees Campaigns + Connections in sidebar, lands on list, sees only shared rows, sees zero action buttons, attempting to direct-URL-hit `/builder/{id}/publish` returns 403 in console (FE shows the existing error toast).
  - **Cross-app** — `voice-rx`-only user does not see inside-sales orchestration entries (unchanged).
  - **System workflow** — anyone with app access sees `mql-concierge-default` in `/system-workflows`; clone route produces a private tenant-owned copy.
- [ ] H-4. Webhook smoke — Bolna/WATI/LSQ webhook callbacks against a live tenant workflow still work end-to-end.
- [ ] H-5. Worker smoke — manual fire of a campaign by an Author runs through `run-workflow` and dispatches successfully.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Ownership rationalization is done halfway and some call sites still think in `created_by` while others think in `user_id` | High | Make this Stage A/B explicit and add dedicated tests proving one canonical owner story |
| Backfill picks the wrong default and a tenant suddenly can't see their own workflows | High if private | Default `shared` for backfill. Tested in migration acceptance |
| `_load_and_gate_*` helpers were not centralized; perm checks scatter and miss an endpoint | Medium | Stage D enumerates every endpoint in a table; tests parametrize over the same list |
| Worker / webhook routes accidentally pull in user perm enforcement | Medium | Stage E-5 and E-6 explicitly verify both bypass; webhooks have their own router and don't import `get_auth_context` |
| Action templates and consent rows are tenant-shared and don't fit the per-row visibility model | Low | Documented as deliberate exception — tenant-wide library, write-gated by perm only |
| Shared workflow references a connection/dataset the current user can no longer read | Low | F-6: render an explicit "Not visible to you" placeholder; don't crash |
| Visibility toggle UI confused with publish state | Medium | Use a different chip color/icon than the publish lifecycle pill from Phase 14 |
| FE perm staleness — admin grants the perm mid-session, user must reload | Medium | Pre-existing gap (`cost:view` etc. share it). Documented; not in scope |
| New PATCH /datasets endpoint conflicts with existing pattern | Low | Mirrors `PATCH /workflows/{id}` shape; reuses `DatasetUpdateRequest` |
| Owner-role assertion drifts (somebody adds a check that doesn't honor `is_owner`) | Low | All checks go through `userHasPermission` / `ensure_permissions`, both of which short-circuit on owner. Tests cover owner |
| Cohort-dataset rows leak across visibility (a private dataset's rows visible via versions endpoint) | Medium | Stage E-3 covers inherited visibility; rows route loads via parent dataset gate |
| Migration leaves `visibility` enum constraint loose | Low | Use existing `asset_visibility` enum from `ShareableMixin`; native_enum=False with check constraint |

---

## Success criteria

After Phase 15 ships:

1. `orchestration:manage` exists in the catalog; admin role-editor shows the toggle.
2. Every orchestration write endpoint (table above) returns 403 to a user without the perm.
3. Edit/delete/share endpoints return 403 to a user with the perm but no ownership.
4. Ownership semantics are structurally aligned: orchestration rows no longer rely on an implicit `created_by` vs `user_id` distinction.
5. List endpoints filter by `?filter=all|private|shared`; default `all` returns own + shared in the user's app_access.
6. Workflow versions / triggers / runs / recipient states inherit parent workflow visibility — verified by tests.
7. Connection secrets stay redacted on GET regardless of visibility.
8. System workflows are visible to all tenants (with the right app), are not editable, and clone route produces a tenant-owned private copy.
9. Read-only viewer can browse Campaigns + Connections list pages and see zero action buttons.
10. Public webhook callbacks and worker job execution are unchanged.
11. Browser smoke matrix (H-3) green.

---

## Post-implementation status (2026-05-08)

Code-side delivery is complete and live. Stages A–F all landed; Stage G has a small doc tail still open. Quick verification map for future readers:

### What shipped
- **Permission catalog** — `orchestration:manage` registered in `backend/app/auth/permission_catalog.py` (group `orchestration`, single grantable entry).
- **Models** — `Workflow`, `ProviderConnection`, `CohortDataset` all mix in `ShareableMixin` (`backend/app/models/orchestration.py`, `backend/app/models/provider_connection.py`). Visibility-aware indexes added alongside (`idx_workflows_tenant_app_visibility_active`, `idx_provider_connections_tenant_app_visibility_active_orm`, `idx_cohort_datasets_tenant_app_visibility`).
- **Asset policy** — orchestration families wired into `backend/app/services/asset_policy.py` (`workflows → workflow`, `provider_connections → connection`, `cohort_datasets → dataset`).
- **Migrations** — shipped as a small chain rather than the single revision the plan envisioned:
  - `0030_orchestration_visibility.py` — adds the columns, FKs, and backfill.
  - `0031_normalize_orchestration_visibility_case.py` — normalizes enum casing across pre-existing rows.
  - `0032_normalize_visibility_defaults.py` — normalizes default-clause drift.
  Net effect matches the plan's intent; the split happened because the case/default cleanup was easier to reason about as separate revisions. Reversible.
- **System workflow visibility** — *not* set via the JSON seeds. The seed loader (`backend/app/services/orchestration_seed.py:375` for insert, `:402` for idempotent update) writes `visibility=Visibility.SHARED` and `shared_by=SYSTEM_USER_ID` programmatically, so adding a key to `mql_concierge_default.json` / `dm2_adherence_watch.json` is intentionally unnecessary.
- **Routes** — every write route gated by `require_permission('orchestration:manage')` across `routes/orchestration.py`, `routes/orchestration_connections.py`, `routes/orchestration_datasets.py`. New `PATCH /datasets/{id}` exists for visibility/name/description toggles. List endpoints accept `?filter=all|private|shared`.
- **Frontend** — gates wired through `src/features/orchestration/utils/access.ts` (`canManageOrchestration`, `canEditOrchestrationAsset`). `WorkflowListPage`, `ConnectionsPage`, `DatasetsPage` render visibility badges, filter pills, and gate Create/Edit/Delete/Share controls. Builder header, run drill-ins, connection forms, and dataset detail surfaces guard their write actions through the same helpers.
- **Tests** — `backend/tests/test_permissions.py` covers the catalog entry and route gates; orchestration suite already exercises clone-then-own and visibility scoping.

### Doc tail still open (low-impact)
- **CLAUDE.md (Stage G-1)** — the cumulative invariant lines about `orchestration:manage`, inherited child-row visibility, and the "secrets stripped regardless of visibility" reminder were not appended. The runtime behavior already enforces all three; this is purely a knowledge-base sync and can be picked up alongside the next CLAUDE.md edit.
- **`docs/plans/orchestration/design-spec.md` (Stage G-2)** — design-spec still describes the pre-Phase-15 auth posture. Update when the next orchestration design pass touches the file.

Both are paperwork, not behavior gaps. Phase 15 acceptance (H-3 smoke matrix) passed at ship time.

---

## Out-of-scope follow-ups

- **Author / Operator / Viewer role split.** If product wants "can run, can't author", introduce `orchestration:run` as a second perm. Phase 16+.
- **Per-row ACLs (Notion-style sharing).** If a tenant needs "share workflow W with user X but not Y", add `orchestration.workflow_shares` table and extend visibility logic.
- **Sharing connections without revealing they exist** (i.e., a third visibility tier "team-private" hiding from non-admins). Not asked; not modeled.
- **FE perm refresh on token refresh.** Replace login-only fetch of `/api/auth/me` with a query that revalidates on focus. Cross-cutting fix; do once for all perms, not per-feature.
- **Audit log of share/unshare events.** `audit_event_logs` table exists; emit a row when visibility flips. Cheap to add later.
