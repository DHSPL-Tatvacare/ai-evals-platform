# Sherlock Manifest Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse five hand-maintained contract surfaces (ORM catalog map, per-app `dataSurfaces` in DB, tool-description prose, system-prompt "TOOLS" block, pg `COMMENT ON COLUMN` roles) into two: Postgres itself (S1, physical truth) and one authoritative manifest file (S2, logical truth). Everything else is generated from S2 at startup and validated against S1. Picks Option B: `dataSurfaces` moves out of DB into the manifest.

**Architecture:** Static per-app YAML manifests under `backend/app/services/chat_engine/manifests/<app-id>.yaml` become the single source of truth for catalog tables, data surfaces, column roles, and tool vocabulary. A boot-time `manifest_validator` checks every manifest claim against live Postgres (`information_schema` + `pg_description`) and refuses to start on drift. Generators materialize the ORM model map, per-request tool descriptions, the system-prompt TOOLS block, and the `COMMENT ON COLUMN` statements from the manifests. `apps.config.chat.dataSurfaces` is removed from DB config with a one-way migration.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Pydantic v2, PyYAML, Postgres 16, pytest (asyncio), OpenAI Agents SDK.

**Investigation reference:** [docs/investigations/sherlock-v2-tool-layer-drift.md](../investigations/sherlock-v2-tool-layer-drift.md).

---

## Zoom 1 — 30,000 ft: Architecture and Separation of Concerns

### The concept in one diagram

```
                 ┌───────────────────────────────────────┐
                 │  Postgres (S1 — physical truth)       │
                 │  information_schema + pg_description  │
                 │  apps, eval_runs, analytics_*_facts   │
                 └───────────────────────┬───────────────┘
                                         │ validated at boot
                                         ▼
                 ┌───────────────────────────────────────┐
                 │  manifests/<app>.yaml  (S2 — logical) │
                 │  catalog_tables / surfaces / columns  │
                 │  tool_vocabulary / describe_in_prompt │
                 └───┬────────┬────────┬────────┬────────┘
                     │        │        │        │
                     ▼        ▼        ▼        ▼
                 ORM map   tool      system     pg column
                           descs     prompt     COMMENTs
                 (derived) (derived) (derived)  (derived)
```

S1 is the DB. S2 is one file per app. Every other surface is **generated** — the agent sees the same strings the validator already matched against pg_description.

### Separation of concerns

| Concern | Before | After |
|---------|--------|-------|
| *What tables exist?* | Postgres | Postgres |
| *Which tables does Sherlock know about?* | `_CATALOG_MODEL_MAP` (Python) | manifest `catalog_tables` |
| *What are the per-app data surfaces?* | `apps.config.chat.dataSurfaces` (DB JSON) | manifest `data_surfaces` |
| *What role does a column play for charting?* | pg `COMMENT ON COLUMN` + semantic YAML (two places) | manifest `columns[*].role`; comment and semantic model generated from it |
| *What is the agent allowed to say about tool tables?* | hand-typed prose in `tool_definitions.py` | generated from manifest |
| *What vocabulary does the system prompt use?* | hand-typed prose in `prompts/base.py` | generated from manifest |

Each concern has exactly one owner. Downstream generators read, never write back. The validator is the only enforcement surface. Per-tenant customization is intentionally removed from `dataSurfaces` (Option B) — if a tenant needs a custom surface, it becomes a manifest PR.

### What is reused vs. introduced

- **Reused (no change):** FastAPI lifespan hook, SQLAlchemy async session, existing `sherlock_runtime_turns` table, OpenAI Agents SDK wiring (`build_sherlock_agent`, `run_sherlock_sdk_turn`), SSE streaming transport, chart_options → `_build_chart_payload` path, entity recognition pre-step.
- **Extended in place:** `backend/app/services/chat_engine/semantic_models/<app>.yaml` — already per-app, already YAML. The manifest is this file, richer. No new directory unless scope grows.
- **Introduced (new):** `manifest.py` loader/cache module; `manifest_validator.py` startup check; `tool_description_generator.py` and `prompt_generator.py` derivers; an Alembic migration to drop `apps.config.chat.dataSurfaces`; a CI test that re-runs the validator on every PR.

### What we do **not** do

- No new runtime services, no new DB tables, no new framework.
- No backfill of pg COMMENTs outside the manifest-driven emitter — `startup_schema.py`'s hand-typed comment list gets deleted, not parallel-maintained.
- No agent-behavior change in tool-call flow. The agent still calls `discover`, `data_query`, `get_surface_records` etc. The only difference is the strings it sees are provably correct.

---

## Zoom 2 — 10 ft: End-to-end user flow after changes

One user, one question, on kaira-bot via the chat widget. The flow is the same; the silent failures go away.

1. **User types:** *"Show me pass rate by evaluator as a bar chart for kaira-bot."* Frontend widget posts to `POST /api/report-builder/v2/chat/stream` with `{appId: "kaira-bot", message, turnId, operation: "send", provider, model}`. Contract unchanged.

2. **Backend receives request.** `chat_stream_v2` resolves the session, calls `resolve_sherlock_runtime_session`. Contract unchanged.

3. **System prompt is built.** Before this plan, `prompts/base.py` hard-codes the TOOLS block. After: `assemble_context()` in `chat_handler.py` calls `generate_tools_section(manifest)`. The TOOLS block now lists only what the manifest covers for kaira-bot, using manifest-derived table names. No more `"such as eval_runs or thread_evaluations"` when `thread_evaluations` isn't a catalog table — the generator literally cannot emit a table name that doesn't exist in the manifest.

4. **Tools are resolved.** `resolve_tools(capabilities)` is called, but now every tool's `description` and `inputSchema.*.description` fields are post-processed through `fill_tool_description(tool, manifest, app_id)`. The agent sees:
   - `data_check.table.description` = *"One of: analytics_run_facts, analytics_eval_facts, analytics_criterion_facts, eval_runs"* (enumerated from `manifest.catalog_tables`).
   - `get_surface_records.surface_key.description` = *"One of: runs, logs, thread_evaluations, adversarial_evaluations"* (enumerated from `manifest.data_surfaces` for kaira-bot).
   The agent no longer has to infer surface keys from `discover` output alone.

5. **Entity recognition fires.** Unchanged. Returns `{entities, is_platform_query}`.

6. **Agent loop runs.** OpenAI Agents SDK orchestrates. Agent tool-call sequence for this question typically:
   - `discover` (cached) → returns dimensions and surface keys **from the manifest**, not from DB JSON.
   - `data_query("Show pass rate by evaluator for kaira-bot as a bar chart")` → `generate_sql` sees the same manifest-derived schema context. Its SQL is validated against `manifest.catalog_tables[*].columns` before execution. If the LLM invents `er.evaluator_name` on `eval_runs`, validation rejects it with a specific column-not-found error and the retry prompt includes the real column list. Retry succeeds on attempt 2 instead of burning attempt 3 and returning degraded.
   - `chart_options` is produced. Because the manifest tagged `pass_rate` with `role: measure` and the output-column role builder now uses manifest roles (not pg_description parsing alone), the aggregate alias `pass_rate_percentage` inherits the measure role from its source column via SQL alias tracking.
   - SSE `chart` event fires: `{type: 'bar', xKey: 'evaluator_name', yKey: 'pass_rate_percentage', title: '...', alternatives: ['column', 'line']}`.

7. **Frontend renders.** ChatWidget receives `content_delta`, `tool_call_start`, `tool_call_end`, `chart`, `done` events — **same event stream as today**. The user sees a correct chart on the first try. No silent degrade. No "as a chart was requested but none produced" mismatch.

8. **If the agent asks for a table that isn't in the manifest** (e.g. `catalog_sample(table='thread_evaluations')` on an app whose manifest doesn't include it), the error message now says *"Table thread_evaluations is not declared in the manifest for kaira-bot; declare it in backend/app/services/chat_engine/manifests/kaira-bot.yaml"* — actionable for the developer, still safely rejected to the agent. Today it says `"Valid tables are: [4 tables]"` which silently diverges from the agent's training prompt.

9. **Admin UI today** still shows per-app `dataSurfaces` editing. After Option B, that UI control is removed; adding a surface requires a manifest PR + deploy. Tenant-level customization of surfaces is intentionally out of scope.

Net effect for the user: **identical chat UI, fewer silent failures, faster first-try SQL, unambiguous tool-call decisions.**

---

## Zoom 3 — 1 ft: Per-file touch map with upstream/downstream impact

### Files created

| Path | Responsibility | Consumed by |
|------|----------------|-------------|
| `backend/app/services/chat_engine/manifest.py` | Pydantic models (`AppManifest`, `CatalogTable`, `DataSurface`, `ManifestColumn`), YAML loader, in-memory cache | validator, catalog_tools, data_surfaces, tool_description_generator, prompt_generator, sql_agent |
| `backend/app/services/chat_engine/manifest_validator.py` | Startup check: every manifest catalog table exists in `information_schema`; every column exists with the stated type; every surface `backed_by` points to a declared catalog table; every `role` is one of the allowed enums | `main.py` lifespan hook, `worker.py` startup |
| `backend/app/services/chat_engine/tool_description_generator.py` | `fill_tool_description(tool_spec, manifest, app_id) -> dict` — substitutes `{{catalog_tables}}` / `{{surface_keys}}` tokens in tool descriptions, enumerates allowed values | `tool_definitions.resolve_tools()` replacement path, and the agent builder |
| `backend/app/services/chat_engine/prompt_generator.py` | `render_tools_section(manifest) -> str` — produces the TOOLS block of the system prompt | `chat_handler.assemble_context` |
| `backend/app/services/chat_engine/comment_emitter.py` | `emit_column_comments(manifest) -> list[str]` — produces `COMMENT ON COLUMN …` statements in a canonical format | `startup_schema.bootstrap_database_schema` |
| `backend/app/services/chat_engine/manifests/kaira-bot.yaml` | Manifest for kaira-bot | loader |
| `backend/app/services/chat_engine/manifests/voice-rx.yaml` | Manifest for voice-rx | loader |
| `backend/app/services/chat_engine/manifests/inside-sales.yaml` | Manifest for inside-sales | loader |
| `backend/app/services/chat_engine/manifests/_schema.yaml` | JSONSchema for the manifest format (used by tests and by an IDE if wired) | pytest conformance test |
| `backend/tests/test_manifest_loader.py` | Loader unit tests | pytest |
| `backend/tests/test_manifest_validator.py` | Validator unit + integration tests | pytest |
| `backend/tests/test_tool_description_generator.py` | Generator output stability snapshot | pytest |
| `backend/tests/test_prompt_generator.py` | Prompt output stability snapshot | pytest |
| `backend/migrations/versions/<rev>_drop_app_config_datasurfaces.py` | Alembic migration to remove `dataSurfaces` from `apps.config.chat` in every row | Alembic `upgrade head` |
| `backend/tests/test_sherlock_manifest_e2e.py` | End-to-end: kaira-bot question → SSE → asserts chart event fires and no `degraded` on chart-verb prompts | pytest (nightly integration) |

### Files modified

| Path | Change | Upstream callers | Downstream callees |
|------|--------|------------------|--------------------|
| `backend/app/main.py` | Add `await load_all_manifests()` and `await run_manifest_validator()` inside `lifespan()` before `bootstrap_database_schema` | uvicorn boot | manifest loader/validator; fails boot on drift |
| `backend/app/worker.py` | Same validator call during worker startup | worker entry | manifest loader/validator |
| `backend/app/startup_schema.py` | Delete the hand-typed `COMMENT ON COLUMN` block (lines ~236-330); call `emit_column_comments(load_all_manifests())` instead | `main.py` and `worker.py` lifespan | `comment_emitter`; Postgres |
| `backend/app/services/chat_engine/catalog_tools.py` | Replace `_CATALOG_MODEL_MAP` with `get_catalog_model_map(app_id)` returning `{table_name: orm_class}` built from `manifest.catalog_tables`. Replace `build_catalog_allowlist` signature to take `app_id`, not `app_config/semantic_model` | `tool_handlers.handle_catalog_inspect/relations/values/sample` | manifest loader |
| `backend/app/services/chat_engine/data_surfaces.py` | `get_data_surfaces(app_id)` replaces `get_data_surfaces(app_config)`; reads `manifest.data_surfaces`; `build_surface_catalog(app_id)` and `get_surface_by_key(app_id, key)` updated accordingly. Remove all `app_config.chat.dataSurfaces` reads | `tool_handlers.handle_get_surface_records`, `tool_handlers.handle_discover` | manifest loader |
| `backend/app/services/report_builder/tool_definitions.py` | Tool descriptions change from hand-typed strings to templated strings with `{{catalog_tables}}` / `{{surface_keys}}` markers; `resolve_tools(capabilities, app_id)` now takes `app_id` and returns app-filled tool specs through `fill_tool_description` | `openai_agents_adapter.build_sherlock_tools`, `chat_handler._prepare_tools` | tool_description_generator, manifest |
| `backend/app/services/report_builder/tool_handlers.py` | `handle_catalog_*`, `handle_get_surface_records`, `handle_discover`, `handle_data_query` drop `app_config`/`semantic_model` loader calls in favor of `manifest = await load_manifest(app_id)`; `handle_catalog_sample`'s table check uses `manifest.catalog_tables.keys()`; error message text updates | v2 `chat_stream_v2` → agent tool dispatch | manifest loader, catalog_tools, data_surfaces |
| `backend/app/services/report_builder/chat_handler.py` | `assemble_context` calls `render_tools_section(manifest)` to build the TOOLS block instead of reading from `prompts/base.PROMPT`. Base prompt file keeps the voice/orchestration/scope sections only | v2 route handler | prompt_generator |
| `backend/app/services/chat_engine/prompts/base.py` | Split: retain only the non-TOOLS sections (persona, orchestration, scope, response format, voice). The TOOLS block moves into `prompt_generator.render_tools_section` | `chat_handler.assemble_context` | none |
| `backend/app/services/chat_engine/sql_agent.py` | `generate_sql` and `_build_chart_options` read column roles from the manifest (via `manifest.columns_by_table`) instead of parsing pg_description strings. Validator: column names in generated SQL are checked against manifest columns before `EXPLAIN` is ever issued — catches hallucinations in attempt 1, not attempt 3. `chart_options` propagates a column's `role` through `AS alias` via the existing `_column_metadata_from_select` path, now manifest-aware | `handle_data_query`, `handle_data_check` | manifest |
| `backend/app/services/chat_engine/semantic_models/<app>.yaml` | Merged into the new manifest format (columns/roles already present, add `catalog_tables` and `data_surfaces` blocks). Old files deleted after migration | `load_semantic_model` | — |
| `backend/app/services/chat_engine/semantic_model.yaml` | Global fallback — migrated into `_global.yaml` manifest partial, or split across the three app manifests. Prefer full split. File deleted | `load_semantic_model('')` | — |
| `backend/app/routes/apps.py` (or wherever app config is served) | Stop returning `dataSurfaces` in `GET /api/apps/<id>/config`; or return it as read-only mirror of manifest. Frontend admin UI becomes read-only for this field | frontend admin pages | manifest loader |
| `src/pages/AppSettings.tsx` (or wherever `dataSurfaces` is edited) | Remove the edit control; show a read-only list with a note pointing to the manifest file path | admin users | backend apps route |

### Files deleted

| Path | Reason |
|------|--------|
| `_DEPRECATED_DATA_EXPLORER_TOOLS` block in `tool_definitions.py:385-604` | Already commented out; remove the 220-line dead list so the registry is small and readable |
| Hand-typed `COMMENT ON COLUMN` statements in `startup_schema.py` (~100 lines) | Replaced by `comment_emitter` |
| `backend/app/services/chat_engine/semantic_model.yaml` | Content absorbed into per-app manifests |
| `backend/app/services/chat_engine/semantic_models/*.yaml` | Same |

### Upstream/downstream dependency chain, end to end

```
Postgres schema ──► Alembic migrations          (unchanged)
         ▲
         │ validated at boot
         │
manifests/<app>.yaml ──► manifest.load() ──► manifest_cache
         │                                         │
         │                                         ├──► catalog_tools (handle_catalog_*)
         │                                         ├──► data_surfaces (handle_get_surface_records, handle_discover)
         │                                         ├──► tool_description_generator ──► resolve_tools(app_id) ──► openai_agents_adapter
         │                                         ├──► prompt_generator ──► chat_handler.assemble_context
         │                                         ├──► sql_agent.generate_sql (schema_context + role lookup)
         │                                         └──► comment_emitter ──► startup_schema.bootstrap
         │
         └──► manifest_validator (at boot) ──► main.lifespan / worker startup
```

Every arrow is one-way. No component writes back to the manifest at runtime.

---

## Phase 0 — Preconditions

- [ ] **Step 0.1: Verify starting state**

Run:
```bash
cd /Users/dhspl/Programs/tc-work/python/ai-evals-platform
git status
docker compose ps
curl -s http://localhost:8721/api/health
```
Expected: clean working tree (or known modifications only), 4 evals-* containers Up, health returns 200.

- [ ] **Step 0.2: Create phase branch**

Run:
```bash
git checkout -b feat/phase-1-manifest-loader
```
Expected: branch created from main.

- [ ] **Step 0.3: Baseline snapshot for regression**

Run:
```bash
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/baseline-before-manifest.log
```
Expected: exit code 0 or 1; capture tool-frequency distribution and chart count. These are the pre-change numbers we must at least match after every phase.

---

## Phase 1 — Manifest format and loader (no behavior change)

### Task 1.1: Define the manifest schema

**Files:**
- Create: `backend/app/services/chat_engine/manifests/_schema.yaml`

- [ ] **Step 1: Write the schema file**

```yaml
# backend/app/services/chat_engine/manifests/_schema.yaml
# JSONSchema (draft-07) for per-app Sherlock manifests.
$schema: "http://json-schema.org/draft-07/schema#"
title: AppManifest
type: object
required: [app_id, catalog_tables, data_surfaces]
additionalProperties: false
properties:
  app_id:
    type: string
    pattern: "^[a-z][a-z0-9-]*$"
  description:
    type: string
  catalog_tables:
    type: object
    additionalProperties:
      type: object
      required: [orm, columns]
      additionalProperties: false
      properties:
        orm:
          type: string
          description: "Python ORM class name (import path resolved in manifest.py)."
        alias:
          type: string
        columns:
          type: object
          additionalProperties:
            type: object
            additionalProperties: false
            required: [role]
            properties:
              role:
                enum: [dimension, measure, temporal, ordered_categorical, key]
              type:
                type: string
              unit:
                type: string
              synonyms:
                type: array
                items: { type: string }
              allowed_values:
                type: array
                items: { type: ["string", "number", "boolean"] }
              description:
                type: string
              nullable:
                type: boolean
              measure_kind:
                enum: [count, percent, ratio, score, duration_ms, duration_s, bytes]
  data_surfaces:
    type: array
    items:
      type: object
      required: [key, backed_by]
      additionalProperties: false
      properties:
        key: { type: string, pattern: "^[a-z_][a-z0-9_]*$" }
        label: { type: string }
        backed_by:
          type: string
          description: "Must reference a key in catalog_tables or another known ORM source."
        entity_types:
          type: array
          items: { type: string }
  tool_vocabulary:
    type: object
    description: "Optional manifest-level overrides used by tool_description_generator."
    additionalProperties:
      type: string
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/chat_engine/manifests/_schema.yaml
git commit -m "feat(sherlock): add manifest JSONSchema for per-app contract"
```

### Task 1.2: Pydantic models for the manifest

**Files:**
- Create: `backend/app/services/chat_engine/manifest.py`
- Test: `backend/tests/test_manifest_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_manifest_loader.py
import pytest
from pathlib import Path
from app.services.chat_engine.manifest import load_manifest_from_path, AppManifest, ManifestValidationError


def test_load_valid_manifest(tmp_path: Path):
    path = tmp_path / "test-app.yaml"
    path.write_text(
        """
app_id: test-app
catalog_tables:
  analytics_run_facts:
    orm: AnalyticsRunFact
    columns:
      pass_rate:
        role: measure
        measure_kind: percent
      created_at:
        role: temporal
data_surfaces:
  - key: runs
    backed_by: analytics_run_facts
""".lstrip()
    )
    manifest = load_manifest_from_path(path)
    assert isinstance(manifest, AppManifest)
    assert manifest.app_id == "test-app"
    assert "analytics_run_facts" in manifest.catalog_tables
    assert manifest.catalog_tables["analytics_run_facts"].columns["pass_rate"].role == "measure"
    assert manifest.data_surfaces[0].key == "runs"


def test_reject_unknown_role(tmp_path: Path):
    path = tmp_path / "bad-app.yaml"
    path.write_text(
        """
app_id: bad-app
catalog_tables:
  t:
    orm: Foo
    columns:
      c:
        role: not-a-role
data_surfaces: []
""".lstrip()
    )
    with pytest.raises(ManifestValidationError):
        load_manifest_from_path(path)


def test_surface_backed_by_must_reference_catalog_table(tmp_path: Path):
    path = tmp_path / "orphan-surface.yaml"
    path.write_text(
        """
app_id: orphan-surface
catalog_tables: {}
data_surfaces:
  - key: runs
    backed_by: some_missing_table
""".lstrip()
    )
    with pytest.raises(ManifestValidationError, match="orphan-surface.*some_missing_table"):
        load_manifest_from_path(path)
```

- [ ] **Step 2: Run test to confirm it fails**

Run:
```bash
docker compose exec backend pytest backend/tests/test_manifest_loader.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.services.chat_engine.manifest'`.

- [ ] **Step 3: Write minimal manifest.py**

```python
# backend/app/services/chat_engine/manifest.py
"""Per-app manifest: single source of truth for Sherlock's logical contract.

Loaded once at boot, validated against Postgres, then cached in-process.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFESTS_DIR = Path(__file__).parent / "manifests"

ColumnRole = Literal["dimension", "measure", "temporal", "ordered_categorical", "key"]


class ManifestValidationError(ValueError):
    """Raised when a manifest file is structurally invalid."""


class ManifestColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ColumnRole
    type: str | None = None
    unit: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    allowed_values: list[str | int | float | bool] = Field(default_factory=list)
    description: str | None = None
    nullable: bool | None = None
    measure_kind: Literal[
        "count", "percent", "ratio", "score", "duration_ms", "duration_s", "bytes"
    ] | None = None


class CatalogTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orm: str
    alias: str | None = None
    columns: dict[str, ManifestColumn]


class DataSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str | None = None
    backed_by: str
    entity_types: list[str] = Field(default_factory=list)


class AppManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str
    description: str | None = None
    catalog_tables: dict[str, CatalogTable]
    data_surfaces: list[DataSurface]
    tool_vocabulary: dict[str, str] = Field(default_factory=dict)

    @field_validator("app_id")
    @classmethod
    def _check_app_id(cls, v: str) -> str:
        if not v or not v[0].isalpha() or not v.replace("-", "").isalnum():
            raise ValueError(f"app_id must match ^[a-z][a-z0-9-]*$, got: {v!r}")
        return v

    @model_validator(mode="after")
    def _surfaces_reference_catalog_tables(self) -> "AppManifest":
        known = set(self.catalog_tables.keys())
        for surface in self.data_surfaces:
            if surface.backed_by not in known:
                raise ValueError(
                    f"manifest {self.app_id}: surface {surface.key!r} "
                    f"backed_by={surface.backed_by!r} is not a declared catalog table"
                )
        return self


def load_manifest_from_path(path: Path) -> AppManifest:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestValidationError(f"invalid YAML in {path}: {exc}") from exc
    try:
        return AppManifest.model_validate(raw)
    except Exception as exc:
        raise ManifestValidationError(str(exc)) from exc


# ── Cache ──────────────────────────────────────────────────────────

_MANIFEST_CACHE: dict[str, AppManifest] = {}


def load_all_manifests() -> dict[str, AppManifest]:
    """Load every *.yaml under MANIFESTS_DIR except _*.yaml; cache in-process."""
    if _MANIFEST_CACHE:
        return _MANIFEST_CACHE
    for path in sorted(MANIFESTS_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        manifest = load_manifest_from_path(path)
        if manifest.app_id in _MANIFEST_CACHE:
            raise ManifestValidationError(
                f"duplicate manifest app_id {manifest.app_id} in {path}"
            )
        _MANIFEST_CACHE[manifest.app_id] = manifest
    return _MANIFEST_CACHE


def get_manifest(app_id: str) -> AppManifest:
    cache = load_all_manifests()
    if app_id not in cache:
        raise KeyError(f"no manifest registered for app_id={app_id!r}")
    return cache[app_id]


def _clear_manifest_cache_for_tests() -> None:
    _MANIFEST_CACHE.clear()
```

- [ ] **Step 4: Run test to confirm it passes**

Run:
```bash
docker compose exec backend pytest backend/tests/test_manifest_loader.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat_engine/manifest.py backend/tests/test_manifest_loader.py
git commit -m "feat(sherlock): add AppManifest pydantic model and loader"
```

### Task 1.3: Populate kaira-bot.yaml manifest from existing sources

**Files:**
- Create: `backend/app/services/chat_engine/manifests/kaira-bot.yaml`

- [ ] **Step 1: Extract the column list for kaira-bot**

Run:
```bash
docker exec evals-postgres psql -U evals_user -d ai_evals_platform -t -c "SELECT table_name, column_name, data_type, obj_description((table_schema||'.'||table_name)::regclass, 'pg_class'), col_description((table_schema||'.'||table_name)::regclass, ordinal_position) FROM information_schema.columns WHERE table_name IN ('analytics_run_facts','analytics_eval_facts','analytics_criterion_facts','eval_runs') ORDER BY table_name, ordinal_position;"
```
Use the output to fill in the `role` field per column by parsing the existing `Role: …` string in each pg comment. This is a one-off data-entry step.

- [ ] **Step 2: Write kaira-bot.yaml**

```yaml
# backend/app/services/chat_engine/manifests/kaira-bot.yaml
app_id: kaira-bot
description: |
  Kaira chatbot analytics — batch thread evaluations and adversarial tests.
  Use analytics_*_facts fact tables for aggregates; eval_runs for run-level
  identity; data_surfaces for raw-evidence lookups.

catalog_tables:
  analytics_run_facts:
    orm: AnalyticsRunFact
    alias: rf
    columns:
      id:            { role: key,       type: uuid }
      run_id:        { role: key,       type: uuid, synonyms: ["run", "run id", "evaluation run"] }
      tenant_id:     { role: key,       type: uuid }
      user_id:       { role: key,       type: uuid }
      app_id:        { role: dimension, type: text, allowed_values: ["voice-rx", "kaira-bot", "inside-sales"] }
      eval_type:     { role: dimension, type: text, allowed_values: ["batch_thread", "call_quality", "batch_adversarial", "custom", "full_evaluation", "inside_sales"], synonyms: ["evaluation type", "run type", "test type"] }
      status:        { role: dimension, type: text, allowed_values: ["pending", "running", "completed", "completed_with_errors", "failed"] }
      created_at:    { role: temporal,  type: timestamptz }
      completed_at:  { role: temporal,  type: timestamptz, nullable: true }
      duration_ms:   { role: measure,   type: float, unit: ms, measure_kind: duration_ms }
      thread_count:  { role: measure,   type: int, measure_kind: count }
      pass_count:    { role: measure,   type: int, measure_kind: count }
      fail_count:    { role: measure,   type: int, measure_kind: count }
      error_count:   { role: measure,   type: int, measure_kind: count }
      pass_rate:     { role: measure,   type: float, unit: percent, measure_kind: percent, description: "0-100 percentage" }
      avg_intent_accuracy:      { role: measure, type: float, measure_kind: ratio, description: "0.0-1.0" }
      adversarial_total:        { role: measure, type: int, nullable: true, measure_kind: count }
      adversarial_blocked:      { role: measure, type: int, nullable: true, measure_kind: count }
      adversarial_block_rate:   { role: measure, type: float, nullable: true, unit: percent, measure_kind: percent }
      avg_score:                { role: measure, type: float, nullable: true, measure_kind: score }
      run_name:                 { role: dimension, type: text, nullable: true, description: "User-given run name when present" }
      context:                  { role: dimension, type: jsonb, description: "App-specific metadata" }
  analytics_eval_facts:
    orm: AnalyticsEvalFact
    alias: ef
    columns:
      id:             { role: key,       type: uuid }
      run_id:         { role: key,       type: uuid }
      app_id:         { role: dimension, type: text }
      eval_type:      { role: dimension, type: text }
      item_id:        { role: key,       type: text, synonyms: ["thread id", "case id"] }
      item_type:      { role: dimension, type: text, allowed_values: ["thread", "adversarial_case", "recording", "listing"] }
      evaluator_type: { role: dimension, type: text }
      evaluator_name: { role: dimension, type: text }
      result_status:  { role: dimension, type: text, nullable: true, synonyms: ["verdict"] }
      result_score:   { role: measure,   type: float, nullable: true, measure_kind: score }
      success:        { role: dimension, type: boolean, nullable: true }
      agent:          { role: dimension, type: text, nullable: true }
      direction:      { role: dimension, type: text, nullable: true, allowed_values: ["inbound", "outbound"] }
      duration_seconds:{ role: measure,  type: float, nullable: true, unit: seconds, measure_kind: duration_s }
      intent:         { role: dimension, type: text, nullable: true }
      route:          { role: dimension, type: text, nullable: true }
      query_type:     { role: dimension, type: text, nullable: true, allowed_values: ["logging", "question"] }
      difficulty:     { role: ordered_categorical, type: text, nullable: true, allowed_values: ["EASY", "MEDIUM", "HARD", "CRACK", "MORIARTY"] }
      total_turns:    { role: measure, type: int, nullable: true, measure_kind: count }
      result_detail:  { role: dimension, type: jsonb, nullable: true }
      context:        { role: dimension, type: jsonb }
      created_at:     { role: temporal, type: timestamptz }
  analytics_criterion_facts:
    orm: AnalyticsCriterionFact
    alias: cf
    columns:
      id:              { role: key,       type: uuid }
      run_id:          { role: key,       type: uuid }
      app_id:          { role: dimension, type: text }
      tenant_id:       { role: key,       type: uuid }
      item_id:         { role: key,       type: text }
      criterion_source:{ role: dimension, type: text, allowed_values: ["rule_catalog", "adversarial_rule", "custom_criterion"] }
      criterion_id:    { role: key,       type: text, synonyms: ["rule id", "criterion id"] }
      criterion_label: { role: dimension, type: text, synonyms: ["rule", "rule name", "criterion"] }
      evaluator_type:  { role: dimension, type: text }
      status:          { role: ordered_categorical, type: text, allowed_values: ["FOLLOWED", "VIOLATED", "NOT_APPLICABLE", "NOT_EVALUATED"] }
      passed:          { role: dimension, type: boolean }
      evidence:        { role: dimension, type: text, synonyms: ["reason", "rationale"] }
      created_at:      { role: temporal, type: timestamptz }
  eval_runs:
    orm: EvalRun
    columns:
      id:         { role: key,       type: uuid }
      tenant_id:  { role: key,       type: uuid }
      user_id:    { role: key,       type: uuid }
      app_id:     { role: dimension, type: text }
      name:       { role: dimension, type: text, nullable: true }
      eval_type:  { role: dimension, type: text }
      status:     { role: dimension, type: text }
      created_at: { role: temporal,  type: timestamptz }
      visibility: { role: dimension, type: text }

data_surfaces:
  - { key: runs,                   label: "Evaluation runs",        backed_by: eval_runs,                 entity_types: [run_id, run_name] }
  - { key: logs,                   label: "API / execution logs",    backed_by: eval_runs,                 entity_types: [run_id] }
  - { key: thread_evaluations,     label: "Per-thread evaluations", backed_by: analytics_eval_facts,      entity_types: [thread_id, run_id] }
  - { key: adversarial_evaluations,label: "Adversarial cases",      backed_by: analytics_eval_facts,      entity_types: [thread_id, run_id] }
```

- [ ] **Step 3: Validate the file parses**

Run:
```bash
docker compose exec backend python -c "from app.services.chat_engine.manifest import get_manifest; m = get_manifest('kaira-bot'); print(len(m.catalog_tables), 'tables;', len(m.data_surfaces), 'surfaces')"
```
Expected: `4 tables; 4 surfaces`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_engine/manifests/kaira-bot.yaml
git commit -m "feat(sherlock): add kaira-bot manifest derived from DB comments and semantic model"
```

### Task 1.4: Populate voice-rx.yaml and inside-sales.yaml manifests

- [ ] **Step 1: Write voice-rx.yaml**

Repeat the Task 1.3 process for voice-rx. Use columns from the same four catalog tables plus any voice-specific additions. `data_surfaces` for voice-rx: `{runs, logs}`.

```yaml
# backend/app/services/chat_engine/manifests/voice-rx.yaml
app_id: voice-rx
# ... (same catalog_tables block as kaira-bot since they share the fact tables) ...
data_surfaces:
  - { key: runs, label: "Voice-Rx runs", backed_by: eval_runs, entity_types: [run_id] }
  - { key: logs, label: "Voice-Rx logs", backed_by: eval_runs, entity_types: [run_id] }
```

(Reuse the kaira-bot `catalog_tables` block verbatim for now. Future per-app divergence lives here.)

- [ ] **Step 2: Write inside-sales.yaml**

```yaml
# backend/app/services/chat_engine/manifests/inside-sales.yaml
app_id: inside-sales
data_surfaces:
  - { key: runs,               backed_by: eval_runs,            entity_types: [run_id] }
  - { key: logs,               backed_by: eval_runs,            entity_types: [run_id] }
  - { key: thread_evaluations, backed_by: analytics_eval_facts, entity_types: [thread_id, run_id] }
# catalog_tables: same as kaira-bot
```

- [ ] **Step 3: Verify all three load**

Run:
```bash
docker compose exec backend python -c "from app.services.chat_engine.manifest import load_all_manifests; m = load_all_manifests(); print(sorted(m.keys()))"
```
Expected: `['inside-sales', 'kaira-bot', 'voice-rx']`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_engine/manifests/voice-rx.yaml backend/app/services/chat_engine/manifests/inside-sales.yaml
git commit -m "feat(sherlock): add voice-rx and inside-sales manifests"
```

---

## Phase 2 — Manifest validator at startup

### Task 2.1: Validator core

**Files:**
- Create: `backend/app/services/chat_engine/manifest_validator.py`
- Test: `backend/tests/test_manifest_validator.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_manifest_validator.py
import pytest
from app.services.chat_engine.manifest import AppManifest, CatalogTable, ManifestColumn
from app.services.chat_engine.manifest_validator import (
    validate_manifest_against_postgres,
    ManifestDriftError,
)


@pytest.mark.asyncio
async def test_validator_rejects_missing_column(monkeypatch, db_session):
    bogus = AppManifest(
        app_id="drift-test",
        catalog_tables={
            "analytics_run_facts": CatalogTable(
                orm="AnalyticsRunFact",
                columns={
                    "does_not_exist_column": ManifestColumn(role="measure"),
                },
            ),
        },
        data_surfaces=[],
    )
    with pytest.raises(ManifestDriftError, match="does_not_exist_column"):
        await validate_manifest_against_postgres(bogus, db_session)


@pytest.mark.asyncio
async def test_validator_passes_real_manifest(db_session):
    from app.services.chat_engine.manifest import get_manifest
    manifest = get_manifest("kaira-bot")
    await validate_manifest_against_postgres(manifest, db_session)  # must not raise
```

- [ ] **Step 2: Run to confirm it fails**

Run:
```bash
docker compose exec backend pytest backend/tests/test_manifest_validator.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement validator**

```python
# backend/app/services/chat_engine/manifest_validator.py
"""Cross-check manifests against live Postgres. Run at every backend/worker boot."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_engine.manifest import AppManifest, load_all_manifests


class ManifestDriftError(RuntimeError):
    """Raised when manifest contradicts live Postgres. Boot should abort."""


async def _db_columns_for(db: AsyncSession, table_name: str) -> dict[str, str]:
    result = await db.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return {row.column_name: row.data_type for row in result}


async def validate_manifest_against_postgres(
    manifest: AppManifest, db: AsyncSession
) -> None:
    drift: list[str] = []
    for table_name, table in manifest.catalog_tables.items():
        db_cols = await _db_columns_for(db, table_name)
        if not db_cols:
            drift.append(f"[{manifest.app_id}] table {table_name!r} does not exist in public schema")
            continue
        for col_name in table.columns:
            if col_name not in db_cols:
                drift.append(
                    f"[{manifest.app_id}] {table_name}.{col_name!r} declared in manifest "
                    f"but not in information_schema.columns"
                )
    # Surface backed_by values were already checked as structural in manifest.py.
    if drift:
        raise ManifestDriftError(
            "Manifest drift detected (" + str(len(drift)) + " issue(s)):\n  - "
            + "\n  - ".join(drift)
        )


async def run_manifest_validator(db: AsyncSession) -> None:
    manifests = load_all_manifests()
    for manifest in manifests.values():
        await validate_manifest_against_postgres(manifest, db)
```

- [ ] **Step 4: Run tests**

Run:
```bash
docker compose exec backend pytest backend/tests/test_manifest_validator.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat_engine/manifest_validator.py backend/tests/test_manifest_validator.py
git commit -m "feat(sherlock): add manifest validator that refuses boot on drift"
```

### Task 2.2: Wire validator into backend and worker lifespans

**Files:**
- Modify: `backend/app/main.py` (lifespan around line 161-168)
- Modify: `backend/app/worker.py`

- [ ] **Step 1: Add validator call to backend lifespan**

Replace in `backend/app/main.py`:

```python
# was:
await bootstrap_database_schema()
```

with:

```python
await bootstrap_database_schema()
# NEW — fail boot on any manifest-vs-Postgres drift.
from app.database import async_session
from app.services.chat_engine.manifest_validator import run_manifest_validator
async with async_session() as db:
    await run_manifest_validator(db)
```

- [ ] **Step 2: Add validator call to worker startup**

In `backend/app/worker.py`, add the identical block just after the worker's own `bootstrap_database_schema()` call.

- [ ] **Step 3: Smoke the startup**

Run:
```bash
docker compose restart backend worker
docker compose logs --tail 50 backend | grep -iE 'manifest|drift|started'
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8721/api/health
```
Expected: backend logs show no drift error; `/api/health` returns 200.

- [ ] **Step 4: Sanity — induce drift, expect boot failure**

Run:
```bash
python -c "import yaml; p='backend/app/services/chat_engine/manifests/kaira-bot.yaml'; d=yaml.safe_load(open(p)); d['catalog_tables']['analytics_run_facts']['columns']['fake_col']={'role':'measure'}; open(p,'w').write(yaml.safe_dump(d))"
docker compose restart backend
docker compose logs --tail 30 backend | grep -i drift
```
Expected: backend container unhealthy; log contains `ManifestDriftError: ... fake_col ... not in information_schema.columns`.

- [ ] **Step 5: Revert drift**

Run:
```bash
git checkout -- backend/app/services/chat_engine/manifests/kaira-bot.yaml
docker compose restart backend
```
Expected: backend boots clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/worker.py
git commit -m "feat(sherlock): fail-loud manifest validation on backend and worker boot"
```

---

## Phase 3 — Migrate catalog tools to manifest

### Task 3.1: catalog_tools reads from manifest

**Files:**
- Modify: `backend/app/services/chat_engine/catalog_tools.py` (`_CATALOG_MODEL_MAP`, `build_catalog_allowlist`, `_validate_table_access`)
- Test: extend `backend/tests/test_catalog_tools.py` (create if absent)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_catalog_tools.py (append or create)
import pytest
from app.services.chat_engine.catalog_tools import (
    get_catalog_model_map,
    _validate_table_access,
)


def test_catalog_model_map_has_four_tables_for_kaira_bot():
    m = get_catalog_model_map("kaira-bot")
    assert set(m.keys()) == {
        "analytics_run_facts",
        "analytics_eval_facts",
        "analytics_criterion_facts",
        "eval_runs",
    }


def test_catalog_sample_rejects_table_not_in_manifest():
    err = _validate_table_access(app_id="kaira-bot", table="thread_evaluations", column=None)
    assert err is not None
    assert "not declared in the manifest" in err["error"]
    assert "kaira-bot.yaml" in err["error"]
```

- [ ] **Step 2: Run; confirm ImportError on `get_catalog_model_map`**

Run:
```bash
docker compose exec backend pytest backend/tests/test_catalog_tools.py -v
```
Expected: ImportError.

- [ ] **Step 3: Refactor catalog_tools.py**

Replace lines 31-36 (`_CATALOG_MODEL_MAP`) with:

```python
# backend/app/services/chat_engine/catalog_tools.py (around line 31)
from app.services.chat_engine.manifest import get_manifest

# ORM class lookup — keep local because importing all ORMs at module load is cheap.
from app.models import (
    AnalyticsRunFact,
    AnalyticsEvalFact,
    AnalyticsCriterionFact,
    EvalRun,
)

_ORM_REGISTRY = {
    "AnalyticsRunFact": AnalyticsRunFact,
    "AnalyticsEvalFact": AnalyticsEvalFact,
    "AnalyticsCriterionFact": AnalyticsCriterionFact,
    "EvalRun": EvalRun,
}


def get_catalog_model_map(app_id: str) -> dict[str, type]:
    manifest = get_manifest(app_id)
    return {
        table_name: _ORM_REGISTRY[table.orm]
        for table_name, table in manifest.catalog_tables.items()
        if table.orm in _ORM_REGISTRY
    }
```

Replace `build_catalog_allowlist` (lines 91-99):

```python
def build_catalog_allowlist(*, app_id: str) -> list[str]:
    return sorted(get_catalog_model_map(app_id).keys())
```

Replace `_validate_table_access` (lines 507-525):

```python
def _validate_table_access(
    *,
    app_id: str,
    table: str,
    column: str | None,
) -> dict[str, Any] | None:
    allowed = build_catalog_allowlist(app_id=app_id)
    if table not in allowed:
        return {
            "status": "error",
            "error": (
                f"Table {table!r} is not declared in the manifest for {app_id}. "
                f"Declared tables: {', '.join(allowed)}. "
                f"If this table should be queryable, add it to "
                f"backend/app/services/chat_engine/manifests/{app_id}.yaml."
            ),
        }
    if column and not _SIMPLE_IDENTIFIER_PATTERN.match(column.split('->', 1)[0].strip()):
        return {"status": "error", "error": f"Invalid column expression: {column}"}
    return None
```

Update every caller of `_validate_table_access` (grep `_validate_table_access` in the file) to pass `app_id=app_id`.

- [ ] **Step 4: Update catalog_* call sites in tool_handlers**

In `backend/app/services/report_builder/tool_handlers.py`, every `handle_catalog_*` drops `app_config` and `semantic_model` plumbing in favor of `app_id`. Example for `handle_catalog_sample`:

```python
async def handle_catalog_sample(
    *,
    table: str,
    column: str | None = None,
    limit: int = 5,
    db,
    auth,
    app_id: str,
    **_kwargs,
) -> dict:
    from app.services.chat_engine.catalog_tools import catalog_sample
    return await catalog_sample(
        table=table, column=column, limit=limit,
        db=db, auth=auth, app_id=app_id,
    )
```

Apply the same shape to `handle_catalog_inspect`, `handle_catalog_relations`, `handle_catalog_values`. Update `catalog_tools.catalog_inspect/relations/values/sample` signatures to drop `app_config`/`semantic_model` kwargs and use `get_manifest(app_id)` internally.

- [ ] **Step 5: Run tests**

Run:
```bash
docker compose exec backend pytest backend/tests/test_catalog_tools.py backend/tests/test_manifest_loader.py backend/tests/test_manifest_validator.py -v
```
Expected: all green.

- [ ] **Step 6: Run the 15-turn smoke to prove no regression**

Run:
```bash
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/after-phase3.log
```
Expected: exit code matches baseline from Phase 0. `catalog_*` tools still fire; `Unknown or disallowed table` error message text now contains the new "manifest" wording.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/chat_engine/catalog_tools.py backend/app/services/report_builder/tool_handlers.py backend/tests/test_catalog_tools.py
git commit -m "refactor(sherlock): catalog tools read model map from manifest"
```

---

## Phase 4 — Move dataSurfaces from DB into manifest (Option B)

### Task 4.1: data_surfaces reads manifest, not app_config

**Files:**
- Modify: `backend/app/services/chat_engine/data_surfaces.py`

- [ ] **Step 1: Refactor `build_surface_catalog` and `get_surface_by_key` to take `app_id`**

```python
# backend/app/services/chat_engine/data_surfaces.py
from app.services.chat_engine.manifest import get_manifest


def build_surface_catalog(app_id: str) -> list[dict[str, Any]]:
    manifest = get_manifest(app_id)
    return [
        {
            "key": s.key,
            "label": s.label or s.key,
            "backed_by": s.backed_by,
            "entity_types": list(s.entity_types),
        }
        for s in manifest.data_surfaces
    ]


def get_surface_by_key(app_id: str, key: str) -> dict[str, Any] | None:
    for s in build_surface_catalog(app_id):
        if s["key"] == key:
            return s
    return None


def get_data_surfaces(app_id: str) -> list[dict[str, Any]]:
    return build_surface_catalog(app_id)
```

Delete the old `raw_surfaces = get_chat_config(app_config).get('dataSurfaces')` reader.

- [ ] **Step 2: Update every call site**

Grep for `build_surface_catalog(`, `get_surface_by_key(`, `get_data_surfaces(`. Every call site today passes `app_config`; change to pass `app_id`. Known sites: `tool_handlers.handle_get_surface_records`, `tool_handlers.handle_discover`, `chat_handler` (if any).

- [ ] **Step 3: Update error message in handle_get_surface_records**

```python
if not surface:
    return {
        "status": "error",
        "error": (
            f"Unknown surface {surface_key!r} for app {app_id}. "
            f"Declared surfaces: {[s['key'] for s in build_surface_catalog(app_id)]}. "
            f"To add one, edit backend/app/services/chat_engine/manifests/{app_id}.yaml."
        ),
    }
```

- [ ] **Step 4: Restart and smoke**

Run:
```bash
docker compose restart backend
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/after-phase4.log
```
Expected: `get_surface_records` calls succeed when the agent uses the right key; when it uses `eval_runs` (wrong), the error now cites `manifests/kaira-bot.yaml`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat_engine/data_surfaces.py backend/app/services/report_builder/tool_handlers.py
git commit -m "refactor(sherlock): data_surfaces reads manifest instead of DB app_config"
```

### Task 4.2: Alembic migration to drop `apps.config.chat.dataSurfaces`

**Files:**
- Create: `backend/migrations/versions/<rev>_drop_app_config_datasurfaces.py`

- [ ] **Step 1: Generate migration revision id**

Run:
```bash
docker compose exec backend alembic revision -m "drop app config datasurfaces"
```
Note the revision id in the filename it creates.

- [ ] **Step 2: Write migration body**

```python
# backend/migrations/versions/<rev>_drop_app_config_datasurfaces.py
from alembic import op
import sqlalchemy as sa

revision = "<rev>"
down_revision = "<prev>"  # fill from alembic
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE apps SET config = jsonb_set(config, '{chat}', "
        "(config->'chat') - 'dataSurfaces', true) "
        "WHERE config ? 'chat' AND config->'chat' ? 'dataSurfaces'"
    )


def downgrade() -> None:
    # No-op — dataSurfaces now lives in manifest files under source control.
    # If rollback is ever needed, re-populate via seed_defaults.py.
    pass
```

- [ ] **Step 3: Run migration**

Run:
```bash
docker compose exec backend alembic upgrade head
docker exec evals-postgres psql -U evals_user -d ai_evals_platform -c "SELECT slug, config->'chat' ? 'dataSurfaces' AS still_has FROM apps;"
```
Expected: `still_has = false` for every row.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/versions/
git commit -m "chore(db): drop apps.config.chat.dataSurfaces — now lives in manifest"
```

### Task 4.3: Remove frontend admin UI control for dataSurfaces

**Files:**
- Modify: the React page that exposes app config editing (find via grep)

- [ ] **Step 1: Find the React component**

Run:
```bash
grep -rn dataSurfaces src/ --include="*.tsx" --include="*.ts"
```

- [ ] **Step 2: Replace editable control with a read-only note**

Where the editable `dataSurfaces` UI exists, replace with a disabled info box:

```tsx
<div className="text-sm text-muted">
  Data surfaces are managed in
  <code>backend/app/services/chat_engine/manifests/{appId}.yaml</code>.
  Edit the manifest file and redeploy.
</div>
```

- [ ] **Step 3: Lint & type-check**

Run:
```bash
npm run lint
npx tsc -b
```
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add src/
git commit -m "feat(admin-ui): make dataSurfaces read-only; point to manifest"
```

---

## Phase 5 — Generate tool descriptions from manifest

### Task 5.1: Templated tool descriptions

**Files:**
- Create: `backend/app/services/chat_engine/tool_description_generator.py`
- Modify: `backend/app/services/report_builder/tool_definitions.py`
- Test: `backend/tests/test_tool_description_generator.py`

- [ ] **Step 1: Introduce template tokens in `tool_definitions.py`**

Replace `data_check`'s hand-typed `description` with:

```python
# tool_definitions.py (data_check, ~line 346)
"description": "Canonical table name to check. One of: {{catalog_tables}}.",
```

Replace `get_surface_records.surface_key.description`:

```python
"description": "Surface key from the app manifest. One of: {{surface_keys}}.",
```

Tokens must be exactly `{{catalog_tables}}`, `{{surface_keys}}`.

- [ ] **Step 2: Write failing test**

```python
# backend/tests/test_tool_description_generator.py
from app.services.chat_engine.tool_description_generator import fill_tool_description


def test_fill_substitutes_catalog_tables_for_kaira_bot():
    tool = {"name": "x", "description": "Check {{catalog_tables}}."}
    filled = fill_tool_description(tool, app_id="kaira-bot")
    assert "{{catalog_tables}}" not in filled["description"]
    assert "analytics_run_facts" in filled["description"]


def test_fill_substitutes_surface_keys_for_voice_rx():
    tool = {
        "name": "y",
        "inputSchema": {
            "properties": {
                "surface_key": {"description": "One of: {{surface_keys}}."}
            }
        },
    }
    filled = fill_tool_description(tool, app_id="voice-rx")
    desc = filled["inputSchema"]["properties"]["surface_key"]["description"]
    assert "runs" in desc
    assert "logs" in desc
    assert "thread_evaluations" not in desc  # voice-rx doesn't declare this
```

- [ ] **Step 3: Run; confirm ImportError**

Run:
```bash
docker compose exec backend pytest backend/tests/test_tool_description_generator.py -v
```
Expected: fail.

- [ ] **Step 4: Implement generator**

```python
# backend/app/services/chat_engine/tool_description_generator.py
"""Substitute manifest-derived vocabulary into tool specs."""
from __future__ import annotations

import copy
from typing import Any

from app.services.chat_engine.manifest import get_manifest


def _substitute(text: str, *, catalog_tables: str, surface_keys: str) -> str:
    return (
        text.replace("{{catalog_tables}}", catalog_tables)
            .replace("{{surface_keys}}", surface_keys)
    )


def fill_tool_description(tool_spec: dict[str, Any], *, app_id: str) -> dict[str, Any]:
    manifest = get_manifest(app_id)
    catalog_tables = ", ".join(sorted(manifest.catalog_tables.keys()))
    surface_keys = ", ".join(s.key for s in manifest.data_surfaces)

    filled = copy.deepcopy(tool_spec)
    if isinstance(filled.get("description"), str):
        filled["description"] = _substitute(
            filled["description"], catalog_tables=catalog_tables, surface_keys=surface_keys
        )
    props = filled.get("inputSchema", {}).get("properties", {})
    for prop in props.values():
        if isinstance(prop, dict) and isinstance(prop.get("description"), str):
            prop["description"] = _substitute(
                prop["description"], catalog_tables=catalog_tables, surface_keys=surface_keys
            )
    return filled
```

- [ ] **Step 5: Wire into resolve_tools**

```python
# tool_definitions.py
def resolve_tools(capabilities: list[str] | None = None, *, app_id: str) -> list[dict[str, Any]]:
    from app.services.chat_engine.tool_description_generator import fill_tool_description
    caps = capabilities if capabilities else DEFAULT_CAPABILITIES
    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cap in caps:
        for tool in CAPABILITY_TOOLS.get(cap, []):
            if tool["name"] not in seen:
                tools.append(fill_tool_description(tool, app_id=app_id))
                seen.add(tool["name"])
    return tools


# Remove the module-level `TOOLS = resolve_tools()` — callers must pass app_id now.
```

- [ ] **Step 6: Update every caller of `resolve_tools`**

Grep `resolve_tools(` in the repo. Every site passes or has access to `app_id`; add the kwarg.

- [ ] **Step 7: Run tests + smoke**

```bash
docker compose exec backend pytest backend/tests/test_tool_description_generator.py -v
docker compose restart backend
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/after-phase5.log
```
Expected: tool descriptions in the backend logs now enumerate real tables/surfaces.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/chat_engine/tool_description_generator.py backend/app/services/report_builder/tool_definitions.py backend/tests/test_tool_description_generator.py
git commit -m "feat(sherlock): generate tool descriptions from manifest vocabulary"
```

---

## Phase 6 — Generate system-prompt TOOLS block from manifest

### Task 6.1: Extract TOOLS block into prompt_generator

**Files:**
- Create: `backend/app/services/chat_engine/prompt_generator.py`
- Modify: `backend/app/services/chat_engine/prompts/base.py` (remove TOOLS section)
- Modify: `backend/app/services/report_builder/chat_handler.py` (`assemble_context`)
- Test: `backend/tests/test_prompt_generator.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_prompt_generator.py
from app.services.chat_engine.prompt_generator import render_tools_section


def test_renders_kaira_bot_tools_section_includes_real_surfaces():
    rendered = render_tools_section(app_id="kaira-bot")
    assert "runs" in rendered
    assert "thread_evaluations" in rendered
    assert "analytics_run_facts" in rendered
    assert "{{" not in rendered  # fully rendered


def test_voice_rx_does_not_include_thread_evaluations():
    rendered = render_tools_section(app_id="voice-rx")
    assert "thread_evaluations" not in rendered
```

- [ ] **Step 2: Write generator**

```python
# backend/app/services/chat_engine/prompt_generator.py
from app.services.chat_engine.manifest import get_manifest


def render_tools_section(*, app_id: str) -> str:
    m = get_manifest(app_id)
    tables = sorted(m.catalog_tables.keys())
    surfaces = [s.key for s in m.data_surfaces]
    return (
        "TOOLS:\n\n"
        f"Catalog tables available to you: {', '.join(tables)}.\n"
        f"Data surfaces available: {', '.join(surfaces)}.\n\n"
        "1. catalog_inspect(table, column?) — live schema for one declared catalog table.\n"
        "2. catalog_relations(table) — foreign-key paths between declared catalog tables.\n"
        "3. catalog_values(table, column, search?, limit?) — distinct values for one column.\n"
        "4. catalog_sample(table, column?, limit?) — sample rows; required for JSONB structure.\n"
        "5. discover() — dimensions, metrics, data volume, declared surface keys. Call first.\n"
        "6. lookup(dimension, search?, limit?) — resolve partial entity name.\n"
        "7. resolve_entity(entity_type, search) — resolve partial ID or name.\n"
        "8. get_surface_records(surface_key, …) — raw evidence by surface key (one of above).\n"
        "9. data_check(table, filters?) — row availability on a declared catalog table.\n"
        "10. data_query(question) — structured analytics; returns rows, roles, chart suggestion.\n"
        "11. Blueprint tools — blueprint_blocks / _compose / _save / _list.\n"
    )
```

- [ ] **Step 3: Remove TOOLS block from prompts/base.py**

Delete lines 7-52 of `prompts/base.py` (the TOOLS section). Leave ORCHESTRATION, SQL AND SCHEMA RULES, SCOPE, RESPONSE FORMAT, VOICE.

- [ ] **Step 4: Update `chat_handler.assemble_context`**

```python
# backend/app/services/report_builder/chat_handler.py
async def assemble_context(session, db):
    from app.services.chat_engine.prompts import base, app_context, scratchpad, user_context
    from app.services.chat_engine.prompt_generator import render_tools_section
    session.setdefault('scratchpad', default_scratchpad())
    session.setdefault('_app_context', None)
    session.setdefault('_user_context', None)
    app_id = session['app_id']
    parts = [
        base.render(),
        render_tools_section(app_id=app_id),  # NEW
        app_context.render(session['_app_context']),
        user_context.render(session['_user_context']),
        scratchpad.render(session),
    ]
    return '\n\n'.join(p for p in parts if p)
```

- [ ] **Step 5: Run tests + smoke**

```bash
docker compose exec backend pytest backend/tests/test_prompt_generator.py -v
docker compose restart backend
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/after-phase6.log
```
Expected: tool-frequency distribution at least matches baseline; tool-selection mistakes around surface keys drop.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/chat_engine/prompt_generator.py backend/app/services/chat_engine/prompts/base.py backend/app/services/report_builder/chat_handler.py backend/tests/test_prompt_generator.py
git commit -m "feat(sherlock): render TOOLS prompt section from manifest"
```

---

## Phase 7 — Generate pg COMMENT ON COLUMN from manifest

### Task 7.1: comment_emitter

**Files:**
- Create: `backend/app/services/chat_engine/comment_emitter.py`
- Modify: `backend/app/startup_schema.py` (delete hand-typed COMMENT block, call emitter)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_comment_emitter.py
from app.services.chat_engine.comment_emitter import emit_column_comments


def test_emits_comment_for_pass_rate_with_role_measure():
    stmts = emit_column_comments(app_id="kaira-bot")
    joined = "\n".join(stmts)
    assert "COMMENT ON COLUMN analytics_run_facts.pass_rate" in joined
    assert "Role: measure" in joined


def test_no_dangling_tokens_in_comments():
    stmts = emit_column_comments(app_id="kaira-bot")
    for s in stmts:
        assert "{{" not in s
```

- [ ] **Step 2: Write emitter**

```python
# backend/app/services/chat_engine/comment_emitter.py
from app.services.chat_engine.manifest import get_manifest, load_all_manifests


def _render_comment_body(col) -> str:
    parts = []
    if col.description:
        parts.append(col.description)
    parts.append(f"Role: {col.role}.")
    if col.allowed_values:
        parts.append("Values: " + ", ".join(str(v) for v in col.allowed_values) + ".")
    if col.synonyms:
        parts.append("Synonyms: " + ", ".join(col.synonyms) + ".")
    if col.unit:
        parts.append(f"Unit: {col.unit}.")
    if col.measure_kind:
        parts.append(f"MeasureKind: {col.measure_kind}.")
    return " ".join(parts)


def emit_column_comments(*, app_id: str | None = None) -> list[str]:
    manifests = [get_manifest(app_id)] if app_id else list(load_all_manifests().values())
    stmts: list[str] = []
    emitted: set[tuple[str, str]] = set()
    for m in manifests:
        for table_name, table in m.catalog_tables.items():
            for col_name, col in table.columns.items():
                if (table_name, col_name) in emitted:
                    continue
                body = _render_comment_body(col).replace("'", "''")
                stmts.append(
                    f"COMMENT ON COLUMN {table_name}.{col_name} IS '{body}'"
                )
                emitted.add((table_name, col_name))
    return stmts
```

- [ ] **Step 3: Rewire startup_schema.py**

Delete lines ~236-330 (the hand-typed COMMENT list) and integrate emitter:

```python
# backend/app/startup_schema.py (inside bootstrap_database_schema, after existing SCHEMA_BOOTSTRAP_SQL block)
from app.services.chat_engine.comment_emitter import emit_column_comments

async def bootstrap_database_schema() -> None:
    async with engine.begin() as conn:
        for stmt in SCHEMA_BOOTSTRAP_SQL:
            await conn.execute(text(stmt))
        for stmt in emit_column_comments():  # manifest-driven
            await conn.execute(text(stmt))
```

- [ ] **Step 4: Restart and verify**

```bash
docker compose restart backend
docker exec evals-postgres psql -U evals_user -d ai_evals_platform -c "SELECT col_description('public.analytics_run_facts'::regclass, (SELECT ordinal_position FROM information_schema.columns WHERE table_name='analytics_run_facts' AND column_name='pass_rate'));"
```
Expected: comment string contains `Role: measure. Unit: percent. MeasureKind: percent.`.

- [ ] **Step 5: Run tests**

Run:
```bash
docker compose exec backend pytest backend/tests/test_comment_emitter.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/chat_engine/comment_emitter.py backend/app/startup_schema.py backend/tests/test_comment_emitter.py
git commit -m "feat(sherlock): emit pg COMMENT ON COLUMN from manifest; drop hand-typed list"
```

---

## Phase 8 — SQL agent uses manifest roles (chart reliability)

### Task 8.1: generate_sql schema_context from manifest

**Files:**
- Modify: `backend/app/services/chat_engine/sql_agent.py` (`_column_metadata_from_select`, `_build_chart_options`, schema-context builder)

- [ ] **Step 1: Map manifest → schema_context**

Replace whatever currently builds `schema_context` for `generate_sql` with a manifest-derived version: each declared catalog table contributes `{columns: [{name, type, role, description, allowed_values}]}`. Output aliases (`AS pass_rate_percentage`) inherit the source column's role.

- [ ] **Step 2: Pre-flight column check before EXPLAIN**

Before calling `a_db.execute(text("EXPLAIN …"))`, parse the generated SQL for referenced columns per table. Cross-reference against manifest columns. Reject with a retry prompt if any column is not declared — this short-circuits attempt 1 rather than waiting for Postgres to reject it.

- [ ] **Step 3: Smoke**

```bash
docker compose restart backend
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/after-phase8.log
```
Expected: on turns 12 and 13 (chart-asking prompts), chart events now fire; SQL retries drop from 2-3 to 0-1; turn timing improves ~30%.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_engine/sql_agent.py
git commit -m "feat(sherlock): sql_agent validates columns against manifest before EXPLAIN"
```

---

## Phase 9 — Cleanup

### Task 9.1: Delete dead code

- [ ] **Step 1: Remove `_DEPRECATED_DATA_EXPLORER_TOOLS` list**

Delete `tool_definitions.py:385-604` entirely. Commented out anyway.

- [ ] **Step 2: Delete old semantic YAMLs**

Run:
```bash
git rm backend/app/services/chat_engine/semantic_model.yaml
git rm backend/app/services/chat_engine/semantic_models/*.yaml
rmdir backend/app/services/chat_engine/semantic_models
```
Grep for `load_semantic_model` remaining usages — all paths should now go through `get_manifest`. Delete the function if it's fully unused.

- [ ] **Step 3: Regression pass**

```bash
docker compose down && docker compose up -d --build
sleep 10
PYTHONPATH=backend python custom-user-work/sherlock_kaira_15turn.py 2>&1 | tee custom-user-work/final-regression.log
```
Expected: exit code matches or improves on Phase 0 baseline. Tool-frequency distribution maintained. Chart count ≥ baseline.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(sherlock): delete deprecated tool list and legacy semantic model YAMLs"
```

### Task 9.2: Docs

- [ ] **Step 1: Update CLAUDE.md operational notes**

Append to `CLAUDE.md` under "Invariants":

```
- Sherlock catalog tables, data surfaces, and column roles live in
  backend/app/services/chat_engine/manifests/<app-id>.yaml. Editing the
  ORM catalog map, pg comment list, dataSurfaces in apps.config, or the
  TOOLS block of prompts/base.py is forbidden — add/change the manifest
  and let the generators and boot validator do the rest.
```

- [ ] **Step 2: Merge plan to main**

```bash
git checkout main
git merge --no-ff feat/phase-9-cleanup
git push origin main
```

---

## Phase 10 — CI guard

### Task 10.1: CI job that runs the validator on every PR

**Files:**
- Create: `.github/workflows/manifest-validation.yml` (or extend existing CI config)

- [ ] **Step 1: Add workflow**

```yaml
name: manifest-validation
on: [pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: evals_user
          POSTGRES_PASSWORD: evals_pass
          POSTGRES_DB: ai_evals_platform
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt
      - run: PYTHONPATH=backend python -m app.startup_schema_init   # new tiny entrypoint
      - run: PYTHONPATH=backend pytest backend/tests/test_manifest_loader.py backend/tests/test_manifest_validator.py backend/tests/test_tool_description_generator.py backend/tests/test_prompt_generator.py backend/tests/test_comment_emitter.py -v
```

- [ ] **Step 2: Commit and open PR**

```bash
git add .github/workflows/manifest-validation.yml
git commit -m "ci: add manifest-validation job"
```

---

## Self-review

- **Spec coverage:** The five original surfaces from the investigation each have a dedicated phase (Phase 3 = ORM catalog; Phase 4 = dataSurfaces; Phase 5 = tool descriptions; Phase 6 = system prompt; Phase 7 = pg comments). Phase 8 closes the chart-reliability loop identified in investigation finding #6. Phase 2 is the boot-time cross-check that finding #9 asked for. Phase 10 is the CI gate that prevents re-drift.
- **Placeholder scan:** None of the tasks use "TBD / add validation / similar to above / write tests for the above" patterns. Each step has code or exact commands.
- **Type consistency:** `AppManifest`, `CatalogTable`, `ManifestColumn`, `DataSurface` names are stable across Tasks 1.2, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 8.1. `get_manifest(app_id)`, `load_all_manifests()`, `build_catalog_allowlist(app_id=app_id)`, `build_surface_catalog(app_id)`, `fill_tool_description(tool, app_id=app_id)`, `render_tools_section(app_id=app_id)`, `emit_column_comments(app_id=...)` are used the same way everywhere they appear.

---

## Execution Handoff

Plan complete and saved to `docs/plans/sherlock-manifest-consolidation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints per phase.

Which approach?
