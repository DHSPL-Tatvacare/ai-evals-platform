# Phase 3 — Wizard + Frontend Cleanup

> **Status: ⏳ PENDING.** Do not start until Phase 2 is complete and verified on the same shared branch `feat/llm-credentials-cleanup`. Read the [Phase 1 → Phase 2 handoff brief in README.md](README.md#phase-1--phase-2-handoff-brief) for inherited backend contracts that this phase consumes. Phase 3 owns the only mid-feature migration that deletes data (`0048_drop_llm_settings_rows`) — confirm Phase 2's admin UI has been used to re-enable every tenant's providers before running it in any environment.

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Follow `frontend-design` conventions + the repo Design System Rules.

**Goal:** Slim `LLMConfigSection` to two query-fed dropdowns; rewire the 7 client-side LLM-assist surfaces to the Phase-2 backend endpoints; migrate every live `llmSettingsStore`/legacy LLM consumer; delete all of `src/services/llm/` and `llmSettingsStore`; remove `ProviderConfigCard`; retire the `llm-settings` `application_settings` rows.

**Architecture:** `LLMConfigSection` = provider `<Select>` + model `<Select>` (model gated on provider), fed by `useProviderConfigs`. Client-side LLM calls are gone — the 7 assist surfaces call `/api/llm/assist/*`. No Zustand LLM store, no client-side provider pipeline, no per-user keys.

**Branch:** Continue on `feat/llm-credentials-cleanup` — the same branch Phases 1-2 used. Confirm you are on it (`git branch --show-current`) before touching anything, and that Phase 2 is fully committed here. Commit every task on this branch. Do NOT create a new branch.

**Depends on:** Phase 2 (`aiSettingsApi`, `aiSettingsQueries`, the 3 assist endpoints).

**Platform-plan boundary:** This phase is self-contained. Do not wait for Platform Phase 15. It fully owns the legacy LLM store sweep and uses `src/services/api/aiSettingsQueries.ts` directly until the deferred platform query migration is resumed.

**Check command:** `npm run lint && npx tsc -b`

---

## File Structure

| File | Action |
|---|---|
| `src/components/ui/LLMConfigSection.tsx` | Rewritten — two-row, query-fed. Props `showThinking/thinking/onThinkingChange/onModelsLoading` **removed**. |
| `src/services/api/llmAssistApi.ts` | **New** — client for the 3 `/api/llm/assist/*` endpoints. |
| 7 client-side assist surfaces | Rewired to `llmAssistApi` (no more client-side LLM). |
| `src/services/llm/` (whole dir) | **Deleted** — `pipeline/*`, `GeminiProvider.ts`, `providerRegistry.ts`, `modelDiscovery.ts`, `retryPolicy.ts`, `index.ts`. |
| `src/features/settings/components/ModelSelector.tsx` | **Deleted.** |
| `src/stores/llmSettingsStore.ts` | **Deleted only after grep shows zero live consumers.** |
| `src/stores/index.ts`, `src/app/Providers.tsx`, `src/stores/authStore.ts`, `src/features/chat-widget/ChatWidget.tsx`, `src/features/quickActions/registry.ts`, `src/features/evals/components/AIEvalRequest.tsx`, `src/features/evals/hooks/useEvaluatorRunner.ts`, `src/features/evals/hooks/useAIEvaluation.ts`, `src/features/evalRuns/components/NewBatchEvalOverlay.tsx`, `src/features/evalRuns/components/NewAdversarialOverlay.tsx`, `src/features/settings/hooks/useSettingsForm.ts` | Drop `llmSettingsStore` and replace credential checks with enabled+validated provider data or remove obsolete settings-form wiring. |
| 6 `LLMConfigSection` consumers | Drop removed props; repoint `LLMProvider` type. |
| `EvaluationOverlay.tsx` | Replace direct `ModelSelector` blocks with `LLMConfigSection`. |
| 3 app settings pages | Remove `ProviderConfigCard`; then delete `ProviderConfigCard.tsx`. |
| `backend/app/services/asset_policy.py`, 3 backend test files | Remove `llm-settings` from the asset policy. |
| `src/features/guide/pages/ApiAuth.tsx`, `src/features/guide/pages/Pipelines.tsx`, `src/features/guide/data/brainMap.ts` | Update guide references that describe the old client-side pipeline/store so final grep gates are meaningful. |
| `backend/alembic/versions/0048_drop_llm_settings_rows.py` | **New** — drop the orphaned `application_settings` rows (final cleanup). |
| `backend/app/routes/llm.py` | Delete the now-dead `/discover-models` + `/models` routes. |

---

## Task 1: Rewrite `LLMConfigSection` — two-row, query-fed

**Files:** Modify `src/components/ui/LLMConfigSection.tsx` (full rewrite). Test `src/components/ui/LLMConfigSection.test.tsx`.

**New prop contract** (removed: `showThinking`, `thinking`, `onThinkingChange`, `onModelsLoading`):
```typescript
interface LLMConfigSectionProps {
  provider: LLMProvider | '';
  onProviderChange: (p: LLMProvider) => void;
  model: string;
  onModelChange: (m: string) => void;
  compact?: boolean;
  dropdownDirection?: 'up' | 'down';
}
```

**Behaviour:** reads `useProviderConfigs()`. Row 1 = provider `<Select>`, options = configs `isEnabled && validationStatus === 'ok'`. Row 2 = model `<Select>`, disabled until a provider is chosen, options = that provider's `curatedModels`. Changing provider calls `onModelChange('')`. If no provider is available → inline notice "No LLM provider configured. An admin must set one up in AI Settings." and both rows disabled. No live `/discover-models`, no `llmSettingsStore`.

- [ ] **Step 1: Write the failing test.**

```tsx
// src/components/ui/LLMConfigSection.test.tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LLMConfigSection } from './LLMConfigSection';

vi.mock('@/services/api/aiSettingsQueries', () => ({
  useProviderConfigs: () => ({
    data: [
      { provider: 'openai', isEnabled: true, validationStatus: 'ok', curatedModels: ['gpt-5.4'] },
      { provider: 'gemini', isEnabled: true, validationStatus: 'untested', curatedModels: ['gemini-2.5-pro'] },
      { provider: 'anthropic', isEnabled: false, validationStatus: 'ok', curatedModels: [] },
    ],
    isLoading: false,
  }),
}));

const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>
);

describe('LLMConfigSection', () => {
  it('lists only enabled + validated providers', () => {
    render(wrap(<LLMConfigSection provider="" onProviderChange={vi.fn()} model="" onModelChange={vi.fn()} />));
    expect(screen.getByText('OpenAI')).toBeInTheDocument();
    expect(screen.queryByText('Anthropic')).not.toBeInTheDocument();  // disabled
    expect(screen.queryByText('Gemini')).not.toBeInTheDocument();     // untested
  });

  it('disables the model select until a provider is chosen', () => {
    render(wrap(<LLMConfigSection provider="" onProviderChange={vi.fn()} model="" onModelChange={vi.fn()} />));
    expect(screen.getByLabelText(/model/i)).toBeDisabled();
  });
});
```
> Adapt `<Select>` interaction assertions to the repo's existing `Select` test pattern.

- [ ] **Step 2: Run → FAIL** (component still imports `llmSettingsStore`).

- [ ] **Step 3: Rewrite the component.**

```tsx
// src/components/ui/LLMConfigSection.tsx
import { useMemo } from 'react';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';
import { useProviderConfigs } from '@/services/api/aiSettingsQueries';
import type { LLMProvider } from '@/services/api/aiSettingsApi';

const PROVIDER_LABELS: Record<LLMProvider, string> = {
  openai: 'OpenAI', azure_openai: 'Azure OpenAI', anthropic: 'Anthropic', gemini: 'Gemini',
};

interface LLMConfigSectionProps {
  provider: LLMProvider | '';
  onProviderChange: (p: LLMProvider) => void;
  model: string;
  onModelChange: (m: string) => void;
  compact?: boolean;
  dropdownDirection?: 'up' | 'down';
}

export function LLMConfigSection({
  provider, onProviderChange, model, onModelChange, compact, dropdownDirection,
}: LLMConfigSectionProps) {
  const { data: configs = [], isLoading } = useProviderConfigs();
  const available = useMemo(
    () => configs.filter((c) => c.isEnabled && c.validationStatus === 'ok'), [configs]);
  const models = useMemo(
    () => available.find((c) => c.provider === provider)?.curatedModels ?? [],
    [available, provider]);

  if (!isLoading && available.length === 0) {
    return (
      <div className="text-[13px] text-[var(--text-muted)]">
        No LLM provider configured. An admin must set one up in AI Settings.
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col gap-3', compact && 'gap-2')}>
      <Select
        label="Provider" value={provider} disabled={isLoading}
        dropdownDirection={dropdownDirection}
        options={available.map((c) => ({ value: c.provider, label: PROVIDER_LABELS[c.provider] }))}
        onChange={(value) => { onProviderChange(value as LLMProvider); onModelChange(''); }}
      />
      <Select
        label="Model" value={model} disabled={isLoading || !provider}
        dropdownDirection={dropdownDirection}
        options={models.map((m) => ({ value: m, label: m }))}
        onChange={(value) => onModelChange(value)}
      />
    </div>
  );
}
```
> Adjust `<Select>` prop names (`label`/`options`/`onChange`/`disabled`/`dropdownDirection`) to the actual `src/components/ui/Select.tsx` API.

- [ ] **Step 4: Run → PASS.** `npm run lint && npx tsc -b` — expect type errors in consumers still passing removed props; Task 2 fixes them.

- [ ] **Step 5: Commit.** `git add src/components/ui/LLMConfigSection.tsx src/components/ui/LLMConfigSection.test.tsx && git commit -m "feat(llm-byok): slim LLMConfigSection to two query-fed dropdowns"`

---

## Task 2: Update the 6 `LLMConfigSection` consumers

**Files (modify):** `RunAllOverlay.tsx:3,129`, `LLMConfigStep.tsx:4,99,119`, `IssuesTab.tsx:11,151`, `ReportTab.tsx:4,728`, `PlatformReportRenderer.tsx:26,1180`, `EvaluationOverlay.tsx:20,465` (its direct `ModelSelector` use → Task 3).

For each consumer:
1. **Remove the removed props** from the `<LLMConfigSection>` call: `showThinking`, `thinking`, `onThinkingChange`, `onModelsLoading`. The `provider`/`onProviderChange`/`model`/`onModelChange` wiring is unchanged.
2. **Repoint the `LLMProvider` type import.** The old type came from `@/types` or `@/stores` (the deleted store). Change to `import type { LLMProvider } from '@/services/api/aiSettingsApi'`.
3. **Thinking value** — for any consumer that actually *used* the thinking value: move it to a small local `<Select>` (off/low/mid/high) the consumer owns, bound to the same config field as before. Do NOT re-add it to `LLMConfigSection`. If a consumer no longer needs thinking, drop it.

- [ ] **Step 1: Map usage.** `grep -rn "showThinking\|onThinkingChange\|onModelsLoading" src/features` — note which consumers used the thinking value vs just passed the props.

- [ ] **Step 2: Apply per consumer** (one file at a time): strip removed props, repoint the type, relocate thinking where used.

- [ ] **Step 3: Lint + types.** `npm run lint && npx tsc -b` — no `LLMConfigSection`-prop errors (Task 3 still pending for `EvaluationOverlay`'s `ModelSelector`).

- [ ] **Step 4: Commit.** `git add src/features/voiceRx/components/RunAllOverlay.tsx src/features/evalRuns/components/LLMConfigStep.tsx src/features/evalRuns/components/crossRun/IssuesTab.tsx src/features/evalRuns/components/report/ReportTab.tsx src/features/analytics/components/PlatformReportRenderer.tsx && git commit -m "feat(llm-byok): update LLMConfigSection consumers to slim contract"`

---

## Task 3: Fix `EvaluationOverlay`'s direct `ModelSelector` usage

**Files:** Modify `src/features/evals/components/EvaluationOverlay.tsx:31,502,518,534` (3 direct `<ModelSelector>` blocks).

`EvaluationOverlay` renders `<ModelSelector>` three times for per-provider overrides, fed raw `apiKey`/`azureEndpoint`/`azureDeployments` from the deleted store. Each block is "pick provider + model" — exactly the slim `LLMConfigSection`.

- [ ] **Step 1: Identify what each block writes.** Read lines ~490-540 — each `<ModelSelector>` writes a provider-override slot in the run config.

- [ ] **Step 2: Replace each** with `<LLMConfigSection provider=... onProviderChange=... model=... onModelChange=... />` bound to the same override state. Remove the dead `apiKey`/`azureEndpoint`/`azureApiVersion`/`azureDeployments` plumbing and the `getProviderApiKey` / `ModelSelector` imports.

- [ ] **Step 3: Lint + types + visual.** `npm run lint && npx tsc -b`. Dev server: the evaluation overlay's pickers show only configured providers + curated models; selections persist into the run config.

- [ ] **Step 4: Commit.** `git add src/features/evals/components/EvaluationOverlay.tsx && git commit -m "feat(llm-byok): EvaluationOverlay uses slim LLMConfigSection for overrides"`

---

## Task 4: Rewire the 7 client-side LLM-assist surfaces to the backend

**Files:** Create `src/services/api/llmAssistApi.ts`; modify the 7 surfaces. Test: co-located tests for the rewired hooks where the repo already has them.

**The 7 surfaces and their target endpoint:**
| Surface | Endpoint |
|---|---|
| `PromptGeneratorModal.tsx` | `POST /api/llm/assist/generate-prompt` |
| `SchemaGeneratorModal.tsx` | `POST /api/llm/assist/generate-schema` |
| `SchemaGeneratorInline.tsx` | `POST /api/llm/assist/generate-schema` |
| `schemaService.ts` | `POST /api/llm/assist/generate-schema` |
| `useStructuredExtraction.ts` | `POST /api/llm/assist/extract-structured` |
| `StructuredOutputsView.tsx` | (orchestrator — uses `useStructuredExtraction`) |
| `ExtractionModal.tsx` | (UI only — reads store for `apiKey`/`provider`; repoint to `useProviderConfigs`) |

Each surface previously called `createLLMPipeline()` / `createLLMPipelineWithModel()` and read the API key from `llmSettingsStore`. Now: it calls the backend endpoint via `llmAssistApi`, passing an explicit `provider` + `model` — sourced from a `<LLMConfigSection>` the surface mounts (or, where the surface already has a model field, that field + its provider).

- [ ] **Step 1: Write `llmAssistApi.ts`.**

```typescript
// src/services/api/llmAssistApi.ts
import { apiRequest } from '@/services/api/client';
import type { LLMProvider } from '@/services/api/aiSettingsApi';

type PromptType = 'transcription' | 'evaluation' | 'extraction';

export const llmAssistApi = {
  generatePrompt: (body: {
    provider: LLMProvider; model: string; promptType: PromptType; userIdea: string;
  }) => apiRequest<{ prompt: string }>('/api/llm/assist/generate-prompt',
    { method: 'POST', body: JSON.stringify(body) }),

  generateSchema: (body: {
    provider: LLMProvider; model: string; promptType: PromptType; userIdea: string;
  }) => apiRequest<{ schema: Record<string, unknown> }>('/api/llm/assist/generate-schema',
    { method: 'POST', body: JSON.stringify(body) }),

  extractStructured: (body: {
    provider: LLMProvider; model: string; prompt: string;
    promptType: 'freeform' | 'schema'; inputSource: 'transcript' | 'audio' | 'both';
    transcript?: string; audioBase64?: string; audioMimeType?: string;
  }) => apiRequest<{ result: Record<string, unknown>; status: string; error: string | null }>(
    '/api/llm/assist/extract-structured', { method: 'POST', body: JSON.stringify(body) }),
};
```

- [ ] **Step 2: Rewire `PromptGeneratorModal.tsx`.** Replace the `createLLMPipeline()` + `.invoke()` block with `await llmAssistApi.generatePrompt({ provider, model, promptType, userIdea })`. Add a `<LLMConfigSection>` to the modal so the user picks provider+model (replacing the old hardcoded `gemini-2.0-flash`). Remove the `services/llm` imports.

- [ ] **Step 3: Rewire `SchemaGeneratorModal.tsx` + `SchemaGeneratorInline.tsx`.** Same pattern → `llmAssistApi.generateSchema(...)`. Both mount a `<LLMConfigSection>` for provider+model.

- [ ] **Step 4: Rewire `schemaService.ts`.** It currently takes `modelName` and calls `createLLMPipelineWithModel`. Change its signature to take `{ provider, model, userIdea, promptType }` and call `llmAssistApi.generateSchema`. Update its callers to pass `provider` (grep `schemaService` consumers).

- [ ] **Step 5: Rewire `useStructuredExtraction.ts`.** Replace the `createLLMPipeline()` invocation with `llmAssistApi.extractStructured(...)`. The hook already builds transcript/audio inputs — pass them as `transcript` / `audioBase64` (base64-encode the blob) / `audioMimeType`. Provider+model come from the caller (the extraction UI mounts a `<LLMConfigSection>`).

- [ ] **Step 6: Rewire `ExtractionModal.tsx` + `StructuredOutputsView.tsx`.** `ExtractionModal` reads `useLLMSettingsStore` for `apiKey`/`provider`/`saConfigured` — replace with a `<LLMConfigSection>` for the provider+model choice and drop the apiKey/SA logic (the backend resolves credentials now). `StructuredOutputsView` reads `useLLMSettingsStore()` — replace its credential-presence check with `useProviderConfigs()` (`data.some(c => c.isEnabled && c.validationStatus === 'ok')`); thread provider+model into the `extract` call.

- [ ] **Step 7: Lint + types + grep clean.** `npm run lint && npx tsc -b`. `grep -rn "services/llm\|createLLMPipeline" src/features src/services/schemas` → zero hits.

- [ ] **Step 8: Visual check.** Dev server: open PromptGeneratorModal, SchemaGeneratorModal, the structured-outputs extraction flow — each picks a provider+model and the generation/extraction completes via the backend (network tab shows `/api/llm/assist/*`).

- [ ] **Step 9: Commit.** `git add src/services/api/llmAssistApi.ts src/features/settings/components/PromptGeneratorModal.tsx src/features/settings/components/SchemaGeneratorModal.tsx src/features/settings/components/SchemaGeneratorInline.tsx src/services/schemas/schemaService.ts src/features/structured-outputs && git commit -m "feat(llm-byok): rewire client-side LLM-assist surfaces to backend endpoints"`

---

## Task 5: Delete `src/services/llm/` + `ModelSelector`

**Files:** Delete `src/services/llm/` (entire dir), `src/features/settings/components/ModelSelector.tsx`.

After Tasks 1-4 there are no consumers: `LLMConfigSection` was rewritten, `EvaluationOverlay` converted, the 7 assist surfaces rewired, `modelDiscovery` only fed those. `providerRegistry.ts` + `GeminiProvider.ts` were already dead.

- [ ] **Step 1: Confirm zero consumers.** `grep -rn "services/llm\|ModelSelector" src/` → zero hits.

- [ ] **Step 2: Delete.** `git rm -r src/services/llm && git rm src/features/settings/components/ModelSelector.tsx`

- [ ] **Step 3: Lint + types.** `npm run lint && npx tsc -b` clean.

- [ ] **Step 4: Commit.** `git commit -m "chore(llm-byok): delete client-side LLM pipeline + ModelSelector"`

---

## Task 6: Migrate every legacy LLM store consumer, then delete `llmSettingsStore`

**Files:** Delete `src/stores/llmSettingsStore.ts`; modify every live file returned by the grep in Step 1. Known current consumers include `src/stores/index.ts`, `src/app/Providers.tsx`, `src/stores/authStore.ts`, `src/features/chat-widget/ChatWidget.tsx`, `src/features/quickActions/registry.ts`, `src/features/evals/components/AIEvalRequest.tsx`, `src/features/evals/hooks/useEvaluatorRunner.ts`, `src/features/evals/hooks/useAIEvaluation.ts`, `src/features/evalRuns/components/NewBatchEvalOverlay.tsx`, `src/features/evalRuns/components/NewAdversarialOverlay.tsx`, and `src/features/settings/hooks/useSettingsForm.ts`.

- [ ] **Step 1: Find remaining importers.** `rg "llmSettingsStore|useLLMSettingsStore|hasLLMCredentials|getProviderApiKey|hasProviderCredentials|LLM_PROVIDERS" src` — every hit is in scope. Do not delete the store until this command returns no live-code hits.

- [ ] **Step 2: Apply the replacement rules.**
  - `stores/index.ts:1` — delete the `llmSettingsStore` re-export line.
  - `Providers.tsx:7` — remove the import + the boot-time `loadSettings()` call.
  - `authStore.ts:7` — remove the import + the logout-reset call. Confirm logout already does `queryClient.clear()` (or equivalent); if not, add `queryClient.removeQueries({ queryKey: ['admin','ai-settings'] })` to the logout path.
  - `ChatWidget.tsx:20` — replace `useLLMSettingsStore`/`hasProviderCredentials` with `useProviderConfigs()` and OpenAI-family availability: `data.some(c => c.isEnabled && c.validationStatus === 'ok' && (c.provider === 'openai' || c.provider === 'azure_openai'))`. Delete any `apiKey` plumbing — the backend resolves credentials.
  - `quickActions/registry.ts` — stop passing LLM secret fields into `evaluateActionAvailability`. If a configured-provider requirement is still needed, use `useProviderConfigs()` and pass a derived `{ hasConfiguredLlmProvider: boolean }` source, then update the requirements evaluator only if it actually reads old LLM key names.
  - `AIEvalRequest.tsx`, `useEvaluatorRunner.ts`, `useAIEvaluation.ts`, `NewBatchEvalOverlay.tsx`, `NewAdversarialOverlay.tsx`, `RunAllOverlay.tsx`, `LLMConfigStep.tsx`, `IssuesTab.tsx`, `ReportTab.tsx`, `PlatformReportRenderer.tsx` — replace credential checks with enabled+validated provider checks from `useProviderConfigs()`. Provider/model still come from each flow's local config; credentials never enter component state.
  - `useSettingsForm.ts` — remove LLM settings form wiring entirely. App/global settings still save through their existing stores/APIs until separately migrated.

- [ ] **Step 3: Delete the store.** `git rm src/stores/llmSettingsStore.ts`

- [ ] **Step 4: Lint + types + grep clean.** `rg "llmSettingsStore|useLLMSettingsStore|hasLLMCredentials|getProviderApiKey|hasProviderCredentials|LLM_PROVIDERS" src` → no hits. `npm run lint && npx tsc -b` clean.

- [ ] **Step 5: Commit.** `git add src src/stores/llmSettingsStore.ts && git commit -m "feat(llm-byok): delete llmSettingsStore and migrate BYOK consumers"`

---

## Task 7: Remove `ProviderConfigCard` from the 3 app settings pages

**Files:** Modify `VoiceRxSettingsPage.tsx:8,110`, `KairaBotSettingsPage.tsx:8,111`, `InsideSalesSettings.tsx:8,80`; delete `src/features/settings/components/ProviderConfigCard.tsx`.

- [ ] **Step 1: Remove from all 3 pages.** Delete the `import { ProviderConfigCard }` line and the `<ProviderConfigCard ... />` JSX. Clean up any dangling section header. Optionally add a one-line note "LLM providers are configured by an admin in AI Settings" (link to `/admin/ai-settings` only if the user has `configuration:edit`). Verify each page still renders its other (app-specific) settings.

- [ ] **Step 2: Delete the component.** `grep -rn "ProviderConfigCard" src/` → zero hits, then `git rm src/features/settings/components/ProviderConfigCard.tsx`.

- [ ] **Step 3: Lint + types + visual.** `npm run lint && npx tsc -b`. Dev server: all 3 app settings pages render cleanly without the card.

- [ ] **Step 4: Commit.** `git add src/features/voiceRx/settings/VoiceRxSettingsPage.tsx src/features/kairaBotSettings/components/KairaBotSettingsPage.tsx src/features/insideSalesEval/pages/InsideSalesSettings.tsx && git commit -m "feat(llm-byok): remove per-user ProviderConfigCard from app settings pages"`

---

## Task 8: Update guide references for the new BYOK model

**Files:** Modify `src/features/guide/pages/ApiAuth.tsx`, `src/features/guide/pages/Pipelines.tsx`, `src/features/guide/data/brainMap.ts`.

- [ ] **Step 1: Replace old architecture text.** Remove descriptions that say browser-side `useLLMSettingsStore`, `ProviderConfigCard`, `ModelSelector`, or `src/services/llm/*` are the active LLM path. Replace with: admin-managed tenant provider credentials live in `platform.tenant_llm_providers`; UI flows choose provider+model through `LLMConfigSection`; backend resolves credentials with `resolve_llm_credentials`; prompt/schema/extraction assists call `/api/llm/assist/*`.

- [ ] **Step 2: Update diagrams/data.** In `brainMap.ts`, replace nodes that point to deleted files with nodes for `src/services/api/aiSettingsApi.ts`, `src/services/api/aiSettingsQueries.ts`, `src/services/api/llmAssistApi.ts`, `backend/app/services/llm_credentials/resolver.py`, and `backend/app/routes/admin_ai_settings.py`.

- [ ] **Step 3: Grep guide clean.** `rg "useLLMSettingsStore|ProviderConfigCard|ModelSelector|createLLMPipeline|src/services/llm|settings_helper|get_llm_settings_from_db" src/features/guide` → no hits unless the text is explicitly in a historical migration note.

- [ ] **Step 4: Lint + commit.** `npm run lint && npx tsc -b`; `git add src/features/guide && git commit -m "docs(llm-byok): update guide for tenant BYOK credentials"`.

---

## Task 9: Retire the `llm-settings` rows — asset policy + migration 0048

**Files:** Modify `backend/app/services/asset_policy.py:19`, `backend/tests/test_settings_routes.py`, `backend/tests/test_apps_routes.py`, `backend/tests/test_rule_catalog_routes.py`; create `backend/alembic/versions/0048_drop_llm_settings_rows.py`; modify `backend/app/routes/llm.py` (delete dead routes).

> This is the final cleanup. By now nothing reads `llm-settings` from `application_settings` — Phase 1 moved the backend to `tenant_llm_providers`; Phase 3 deleted the frontend store. Deferring the row deletion to here gave a full rollback window across all three phases.

- [ ] **Step 1: Update `asset_policy.py:19`.** `'settings': AssetPolicy(private_only_keys=frozenset({'llm-settings'}))` → `'settings': AssetPolicy(private_only_keys=frozenset())`. Keep the `'settings'` entry; check other `AssetPolicy(...)` entries for the right "empty" shape.

- [ ] **Step 2: Update the 3 test files.**
  - `test_settings_routes.py:74-75` — `is_private_only_asset_key("settings", "llm-settings")` is now `False`; update the assertion (keep the `rule-catalog` one). Lines 138-142 test that SHARED visibility is denied for `llm-settings` — obsolete, **delete that test**. Line 171 creates a setting with `key="llm-settings"` — change to `"rule-catalog"` or delete if it only existed for `llm-settings`.
  - `test_apps_routes.py:53,137` — `"privateOnlyKeys": ["llm-settings"]` → `[]` in both the fixture and the assertion.
  - `test_rule_catalog_routes.py:41` — `key="llm-settings"` → `key="rule-catalog"`.

- [ ] **Step 3: Write migration 0048.**

```python
# backend/alembic/versions/0048_drop_llm_settings_rows.py
"""drop the orphaned application_settings llm-settings rows

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-14

0047 backfilled tenant_llm_providers from these rows. All readers (backend in
Phase 1, frontend store in Phase 3) are now gone. Downgrade is a no-op — the
data is reconstructable from tenant_llm_providers if ever needed.
"""
from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM platform.application_settings WHERE key = 'llm-settings'"))


def downgrade() -> None:
    pass
```

- [ ] **Step 4: Delete the dead `routes/llm.py` routes.** `/discover-models` and `/models` are now consumer-less (`modelDiscovery.ts` is gone). Delete both route handlers and any helper now unused. Keep `auth-status`. Import-check: `PYTHONPATH=backend python -c "import app.routes.llm" && echo OK`.

- [ ] **Step 5: Run migration + tests.**
```bash
cd backend && alembic upgrade head && cd ..
PYTHONPATH=backend python -m pytest backend/tests/test_settings_routes.py backend/tests/test_apps_routes.py backend/tests/test_rule_catalog_routes.py -v
```
Expected: migration clean; all three test files PASS.

- [ ] **Step 6: Commit.** `git add backend/app/services/asset_policy.py backend/tests/test_settings_routes.py backend/tests/test_apps_routes.py backend/tests/test_rule_catalog_routes.py backend/alembic/versions/0048_drop_llm_settings_rows.py backend/app/routes/llm.py && git commit -m "feat(llm-byok): retire llm-settings rows + asset policy + dead llm routes"`

---

## Task 10: Full-app verification

- [ ] **Step 1: Static checks.**
```bash
npm run lint && npx tsc -b && npm run build
rg "get_llm_settings_from_db|settings_helper" backend/app backend/tests ; echo "backend_refs_exit:$?"
rg "useLLMSettingsStore|llmSettingsStore|ProviderConfigCard|ModelSelector|createLLMPipeline|services/llm" src ; echo "frontend_refs_exit:$?"
rg "llm-settings" backend/app src ; echo "llm_settings_refs_exit:$?"
pyenv activate venv-python-ai-evals-arize && PYTHONPATH=backend python -m pytest backend/tests/ -q
```
Expected: build clean; each `rg` prints nothing and exits 1; backend suite green. If a docs/guide historical note intentionally remains, document the exception in the commit message and keep live code clean.

- [ ] **Step 2: End-to-end on the dev server.** `docker compose up --build`, then:
  1. Admin: `/admin/ai-settings` → enable OpenAI, enter a real key, Test → `ok`, curate 1-2 models, Save.
  2. Any user: evaluator wizard / `EvaluationOverlay` → provider dropdown shows only OpenAI; model dropdown unlocks with the curated models.
  3. Run an evaluation → resolves credentials from `tenant_llm_providers`, completes.
  4. Sherlock works (OpenAI is OpenAI-family). Disable OpenAI, leave only a non-OpenAI provider → Sherlock shows the "requires OpenAI/Azure OpenAI" lock.
  5. PromptGeneratorModal / SchemaGeneratorModal / structured-outputs extraction → each picks provider+model, generation/extraction completes via `/api/llm/assist/*`.
  6. No app settings page shows a per-user LLM key form.

- [ ] **Step 3: Commit any fixes.** `git commit -am "test(llm-byok): full-app verification fixes"`

---

## Phase 3 Done — Verification Checklist

- [ ] `rg "get_llm_settings_from_db|settings_helper" backend/app backend/tests` → zero live-code hits
- [ ] `rg "useLLMSettingsStore|llmSettingsStore|ProviderConfigCard|ModelSelector|createLLMPipeline|services/llm" src` → zero live-code hits
- [ ] `rg "llm-settings" backend/app src` → zero live-code hits
- [ ] `npm run lint && npx tsc -b && npm run build` clean
- [ ] Backend suite green; `alembic upgrade head` (incl. 0048) clean
- [ ] `LLMConfigSection` shows only enabled+validated providers; model gated on provider
- [ ] Evaluations, reports, Sherlock, and all 3 LLM-assist flows run end-to-end resolving credentials server-side
- [ ] No per-user LLM settings surface remains; no client-side LLM calls remain
- [ ] All Phase 3 commits are on `feat/llm-credentials-cleanup`. The whole feature is now on this one branch — it is ready for review and a single merge to `main`.

---

## Whole-Project Done — Final State

- LLM credentials: one encrypted table `(tenant_id, provider)`, admin-managed.
- One resolver: `resolve_llm_credentials(db, tenant_id, provider)`. No `user_id`, no `auth_intent`, no `provider_override`, no env fallback for real tenants.
- Sherlock: BYOK with an OpenAI-family constraint — not a managed island.
- Client-side LLM calls: gone. Prompt/schema generation + structured extraction run server-side via `/api/llm/assist/*`.
- Gemini service account: system tenant only, planned-deprecation.
- Tenant LLM credential/model env fallbacks removed; `LLM_CREDENTIAL_KEY` added and boot-validated; Gemini service-account env path remains system-tenant-only.
- Admin "AI Settings" page is the single control plane; wizards are two dropdowns.
- Parked (separate session): full SA removal, per-tenant SA upload, external secret vault, admin-picked Sherlock model, `chat_engine` default-from-curated-list.
