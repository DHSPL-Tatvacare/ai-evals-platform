# AI Evals Platform Lint Cleanup Inventory

## Run Metadata

- Command: `npm run lint`
- Lint parser: `npm run -s lint -- --format json`
- Total issues: **87**
- Errors: **70**
- Warnings: **17**

## Rule Frequency

| Count | Rule |
|---:|---|
| 33 | `@typescript-eslint/no-explicit-any` |
| 15 | `react-hooks/exhaustive-deps` |
| 12 | `react-hooks/set-state-in-effect` |
| 11 | `@typescript-eslint/no-unused-vars` |
| 6 | `react-refresh/only-export-components` |
| 3 | `react-hooks/static-components` |
| 2 | `react-hooks/refs` |
| 2 | `react-hooks/preserve-manual-memoization` |
| 2 | `(no-rule)` |
| 1 | `no-case-declarations` |

## File Frequency

| Count | File |
|---:|---|
| 10 | `src/features/evalRuns/pages/RunDetail.tsx` |
| 7 | `src/services/llm/GeminiProvider.ts` |
| 6 | `src/features/evalRuns/pages/ThreadDetail.tsx` |
| 5 | `src/features/evalRuns/components/EvalTable.tsx` |
| 3 | `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` |
| 3 | `src/features/kaira/components/ActionChips.tsx` |
| 3 | `src/features/kaira/components/NoticeBox.tsx` |
| 3 | `src/services/api/promptsApi.ts` |
| 3 | `src/services/api/schemasApi.ts` |
| 2 | `src/components/ui/Popover.tsx` |
| 2 | `src/features/evalRuns/components/BatchCustomEvaluatorPicker.tsx` |
| 2 | `src/features/evalRuns/pages/Logs.tsx` |
| 2 | `src/features/evals/components/CreateEvaluatorOverlay.tsx` |
| 2 | `src/features/evals/components/SemanticAuditView.tsx` |
| 2 | `src/features/structured-outputs/components/StructuredOutputsView.tsx` |
| 2 | `src/features/transcript/components/AudioPlayer.tsx` |
| 2 | `src/features/transcript/hooks/useMiniPlayerAudio.ts` |
| 2 | `src/features/voiceRx/components/EnhancedJsonViewer.tsx` |
| 1 | `src/app/pages/ListingPage.tsx` |
| 1 | `src/components/ui/SearchableSelect.tsx` |
| 1 | `src/features/evalRuns/components/CsvUploadStep.tsx` |
| 1 | `src/features/evalRuns/components/EvaluatorPreviewOverlay.tsx` |
| 1 | `src/features/evalRuns/components/NewAdversarialOverlay.tsx` |
| 1 | `src/features/evalRuns/components/RunRowCard.tsx` |
| 1 | `src/features/evalRuns/components/Tooltip.tsx` |
| 1 | `src/features/evalRuns/pages/RunList.tsx` |
| 1 | `src/features/evals/components/ArrayItemConfigModal.tsx` |
| 1 | `src/features/evals/components/EvaluationPreviewOverlay.tsx` |
| 1 | `src/features/evals/components/EvaluatorHistoryListOverlay.tsx` |
| 1 | `src/features/evals/components/EvaluatorMetrics.tsx` |
| 1 | `src/features/evals/components/EvaluatorsView.tsx` |
| 1 | `src/features/evals/components/ExtractedDataPane.tsx` |
| 1 | `src/features/evals/components/field-displays/ArrayDisplay.tsx` |
| 1 | `src/features/evals/hooks/useHumanEvaluation.ts` |
| 1 | `src/features/evals/hooks/useListingMetrics.ts` |
| 1 | `src/features/kaira/components/KairaBotEvaluatorsView.tsx` |
| 1 | `src/features/settings/components/PromptGeneratorModal.tsx` |
| 1 | `src/features/settings/components/SchemaGeneratorModal.tsx` |
| 1 | `src/hooks/useKeyboardShortcuts.ts` |
| 1 | `src/hooks/useResolvedColor.ts` |
| 1 | `src/services/api/evaluatorsApi.ts` |
| 1 | `src/services/api/filesApi.ts` |
| 1 | `src/services/templates/apiVariableExtractor.ts` |
| 1 | `src/utils/evalFormatters.ts` |

## Detailed Inventory (All Issues)

### `src/app/pages/ListingPage.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `121:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useEffect has a missing dependency: 'listing'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/components/ui/Popover.tsx`

- Issue count: **2** (2 errors, 0 warnings)

1. **ERROR** at `63:62` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **ERROR** at `63:68` - `react-hooks/refs`
   - Issue: Error: Cannot access refs during render React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).
   - Likely fix: Do not read/write `ref.current` during render. Move ref mutation/access into effects or event handlers; use state when values affect rendering.

### `src/components/ui/SearchableSelect.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `69:5` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evalRuns/components/BatchCustomEvaluatorPicker.tsx`

- Issue count: **2** (2 errors, 0 warnings)

1. **ERROR** at `38:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.
2. **ERROR** at `60:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evalRuns/components/CsvUploadStep.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `98:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useCallback has a missing dependency: 'sendToBackend'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/evalRuns/components/EvalTable.tsx`

- Issue count: **5** (5 errors, 0 warnings)

1. **ERROR** at `138:100` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **ERROR** at `178:84` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
3. **ERROR** at `238:16` - `react-hooks/static-components`
   - Issue: Error: Cannot create components during render Components created during render will reset their state each time they are created. Declare components outside of render.
   - Likely fix: Hoist nested component declarations (e.g., `SortHeader`) to module scope or convert to inline JSX helpers so components are not recreated every render.
4. **ERROR** at `239:16` - `react-hooks/static-components`
   - Issue: Error: Cannot create components during render Components created during render will reset their state each time they are created. Declare components outside of render.
   - Likely fix: Hoist nested component declarations (e.g., `SortHeader`) to module scope or convert to inline JSX helpers so components are not recreated every render.
5. **ERROR** at `247:16` - `react-hooks/static-components`
   - Issue: Error: Cannot create components during render Components created during render will reset their state each time they are created. Declare components outside of render.
   - Likely fix: Hoist nested component declarations (e.g., `SortHeader`) to module scope or convert to inline JSX helpers so components are not recreated every render.

### `src/features/evalRuns/components/EvaluatorPreviewOverlay.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `261:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evalRuns/components/NewAdversarialOverlay.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `220:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useMemo has missing dependencies: 'extraInstructions' and 'selectedCategories'. Either include them or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/evalRuns/components/NewBatchEvalOverlay.tsx`

- Issue count: **3** (0 errors, 3 warnings)

1. **WARNING** at `90:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useMemo has a missing dependency: 'customEvaluatorIds.length'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.
2. **WARNING** at `159:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useMemo has a missing dependency: 'customEvaluatorIds.length'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.
3. **WARNING** at `273:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useMemo has a missing dependency: 'customEvaluatorIds'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/evalRuns/components/RunRowCard.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `186:43` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/features/evalRuns/components/Tooltip.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `31:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evalRuns/pages/Logs.tsx`

- Issue count: **2** (2 errors, 0 warnings)

1. **ERROR** at `157:17` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **ERROR** at `522:41` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/features/evalRuns/pages/RunDetail.tsx`

- Issue count: **10** (10 errors, 0 warnings)

1. **ERROR** at `135:17` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **ERROR** at `149:65` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
3. **ERROR** at `150:17` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
4. **ERROR** at `257:80` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
5. **ERROR** at `289:82` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
6. **ERROR** at `938:44` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
7. **ERROR** at `967:40` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
8. **ERROR** at `985:39` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
9. **ERROR** at `1007:59` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
10. **ERROR** at `1041:54` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/features/evalRuns/pages/RunList.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `244:17` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/features/evalRuns/pages/ThreadDetail.tsx`

- Issue count: **6** (6 errors, 0 warnings)

1. **ERROR** at `35:5` - `react-hooks/preserve-manual-memoization`
   - Issue: Compilation Skipped: Existing memoization could not be preserved React Compiler has skipped optimizing this component because the existing manual memoization could not be preserved. The inferred dependencies did not match the manually specified dependencies, which could cause the value to change more or less frequently than expected. The inferred dependency was `current`, but the source dependencies were [current?.result]. Inferred less specific property than source.
   - Likely fix: Make manual memoization dependencies match actual inferred dependencies, or remove unnecessary `useMemo` if computation is cheap / compiler can optimize safely.
2. **ERROR** at `194:50` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
3. **ERROR** at `213:39` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
4. **ERROR** at `237:44` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
5. **ERROR** at `270:61` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
6. **ERROR** at `304:56` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/features/evals/components/ArrayItemConfigModal.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `44:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evals/components/CreateEvaluatorOverlay.tsx`

- Issue count: **2** (2 errors, 0 warnings)

1. **ERROR** at `45:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.
2. **ERROR** at `66:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evals/components/EvaluationPreviewOverlay.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `39:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evals/components/EvaluatorHistoryListOverlay.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `39:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useEffect has a missing dependency: 'loadRuns'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/evals/components/EvaluatorMetrics.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `89:7` - `no-case-declarations`
   - Issue: Unexpected lexical declaration in case block.
   - Likely fix: Wrap `case` bodies containing `const`/`let`/`function` declarations in braces (`{ ... }`) to create block scope.

### `src/features/evals/components/EvaluatorsView.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `19:53` - `@typescript-eslint/no-unused-vars`
   - Issue: '_onUpdate' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/features/evals/components/ExtractedDataPane.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `209:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/features/evals/components/SemanticAuditView.tsx`

- Issue count: **2** (0 errors, 2 warnings)

1. **WARNING** at `55:9` - `react-hooks/exhaustive-deps`
   - Issue: The 'critiques' logical expression could make the dependencies of useMemo Hook (at line 61) change on every render. To fix this, wrap the initialization of 'critiques' in its own useMemo() Hook.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.
2. **WARNING** at `55:9` - `react-hooks/exhaustive-deps`
   - Issue: The 'critiques' logical expression could make the dependencies of useMemo Hook (at line 114) change on every render. To fix this, wrap the initialization of 'critiques' in its own useMemo() Hook.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/evals/components/field-displays/ArrayDisplay.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `6:3` - `(no-rule)`
   - Issue: Unused eslint-disable directive (no problems were reported from '@typescript-eslint/no-unused-vars').
   - Likely fix: Remove stale `eslint-disable` comments or scope them to active rules only.

### `src/features/evals/hooks/useHumanEvaluation.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `54:44` - `@typescript-eslint/no-unused-vars`
   - Issue: '_updatedEval' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/features/evals/hooks/useListingMetrics.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `14:18` - `react-hooks/preserve-manual-memoization`
   - Issue: Compilation Skipped: Existing memoization could not be preserved React Compiler has skipped optimizing this component because the existing manual memoization could not be preserved. The inferred dependencies did not match the manually specified dependencies, which could cause the value to change more or less frequently than expected. The inferred dependency was `listing.transcript`, but the source dependencies were [listing?.transcript, aiEval]. Inferred different dependency than source.
   - Likely fix: Make manual memoization dependencies match actual inferred dependencies, or remove unnecessary `useMemo` if computation is cheap / compiler can optimize safely.

### `src/features/kaira/components/ActionChips.tsx`

- Issue count: **3** (3 errors, 0 warnings)

1. **ERROR** at `29:17` - `react-refresh/only-export-components`
   - Issue: Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
   - Likely fix: Move non-component exports (constants/helpers) into a separate module, and keep component files exporting components only to preserve Fast Refresh behavior.
2. **ERROR** at `37:17` - `react-refresh/only-export-components`
   - Issue: Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
   - Likely fix: Move non-component exports (constants/helpers) into a separate module, and keep component files exporting components only to preserve Fast Refresh behavior.
3. **ERROR** at `63:17` - `react-refresh/only-export-components`
   - Issue: Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
   - Likely fix: Move non-component exports (constants/helpers) into a separate module, and keep component files exporting components only to preserve Fast Refresh behavior.

### `src/features/kaira/components/KairaBotEvaluatorsView.tsx`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `25:61` - `@typescript-eslint/no-unused-vars`
   - Issue: '_messages' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/features/kaira/components/NoticeBox.tsx`

- Issue count: **3** (3 errors, 0 warnings)

1. **ERROR** at `29:17` - `react-refresh/only-export-components`
   - Issue: Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
   - Likely fix: Move non-component exports (constants/helpers) into a separate module, and keep component files exporting components only to preserve Fast Refresh behavior.
2. **ERROR** at `37:17` - `react-refresh/only-export-components`
   - Issue: Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
   - Likely fix: Move non-component exports (constants/helpers) into a separate module, and keep component files exporting components only to preserve Fast Refresh behavior.
3. **ERROR** at `48:17` - `react-refresh/only-export-components`
   - Issue: Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components.
   - Likely fix: Move non-component exports (constants/helpers) into a separate module, and keep component files exporting components only to preserve Fast Refresh behavior.

### `src/features/settings/components/PromptGeneratorModal.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `102:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useCallback has a missing dependency: 'handleClose'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/settings/components/SchemaGeneratorModal.tsx`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `120:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useCallback has a missing dependency: 'handleClose'. Either include it or remove the dependency array.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/structured-outputs/components/StructuredOutputsView.tsx`

- Issue count: **2** (0 errors, 2 warnings)

1. **WARNING** at `38:9` - `react-hooks/exhaustive-deps`
   - Issue: The 'references' logical expression could make the dependencies of useCallback Hook (at line 108) change on every render. To fix this, wrap the initialization of 'references' in its own useMemo() Hook.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.
2. **WARNING** at `38:9` - `react-hooks/exhaustive-deps`
   - Issue: The 'references' logical expression could make the dependencies of useCallback Hook (at line 130) change on every render. To fix this, wrap the initialization of 'references' in its own useMemo() Hook.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/transcript/components/AudioPlayer.tsx`

- Issue count: **2** (1 errors, 1 warnings)

1. **ERROR** at `72:35` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **WARNING** at `172:6` - `react-hooks/exhaustive-deps`
   - Issue: React Hook useEffect has missing dependencies: 'onReady' and 'onTimeUpdate'. Either include them or remove the dependency array. If 'onReady' changes too often, find the parent component that defines it and wrap that definition in useCallback.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/features/transcript/hooks/useMiniPlayerAudio.ts`

- Issue count: **2** (2 errors, 0 warnings)

1. **ERROR** at `104:16` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **ERROR** at `117:16` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/features/voiceRx/components/EnhancedJsonViewer.tsx`

- Issue count: **2** (1 errors, 1 warnings)

1. **ERROR** at `52:7` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.
2. **WARNING** at `62:9` - `react-hooks/exhaustive-deps`
   - Issue: The 'currentPath' conditional could make the dependencies of useCallback Hook (at line 67) change on every render. To fix this, wrap the initialization of 'currentPath' in its own useMemo() Hook.
   - Likely fix: Align dependency arrays with all referenced values. If dependency identity changes too often, memoize upstream values/functions (`useMemo`/`useCallback`) and then include them.

### `src/hooks/useKeyboardShortcuts.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `23:3` - `react-hooks/refs`
   - Issue: Error: Cannot access refs during render React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).
   - Likely fix: Do not read/write `ref.current` during render. Move ref mutation/access into effects or event handlers; use state when values affect rendering.

### `src/hooks/useResolvedColor.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `15:5` - `react-hooks/set-state-in-effect`
   - Issue: Error: Calling setState synchronously within an effect can trigger cascading renders Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following: * Update external systems with the latest state from React. * Subscribe for updates from some external system, calling setState in a callback function when external state changes. Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).
   - Likely fix: Avoid synchronous `setState` directly in effects for derived UI state. Prefer deriving value during render, initializing state from props once, moving updates into event handlers, or deferring with refs/transitions only when necessary.

### `src/services/api/evaluatorsApi.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `82:14` - `@typescript-eslint/no-unused-vars`
   - Issue: 'err' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/services/api/filesApi.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `54:35` - `@typescript-eslint/no-unused-vars`
   - Issue: '_listingId' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/services/api/promptsApi.ts`

- Issue count: **3** (3 errors, 0 warnings)

1. **ERROR** at `54:14` - `@typescript-eslint/no-unused-vars`
   - Issue: 'err' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.
2. **ERROR** at `81:27` - `@typescript-eslint/no-unused-vars`
   - Issue: '_appId' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.
3. **ERROR** at `81:42` - `@typescript-eslint/no-unused-vars`
   - Issue: '_id' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/services/api/schemasApi.ts`

- Issue count: **3** (3 errors, 0 warnings)

1. **ERROR** at `57:14` - `@typescript-eslint/no-unused-vars`
   - Issue: 'err' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.
2. **ERROR** at `84:27` - `@typescript-eslint/no-unused-vars`
   - Issue: '_appId' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.
3. **ERROR** at `84:42` - `@typescript-eslint/no-unused-vars`
   - Issue: '_id' is defined but never used.
   - Likely fix: Remove unused bindings, or refactor signatures so only needed params remain. If an argument is required by an interface, consume it intentionally or adjust lint config for ignore patterns.

### `src/services/llm/GeminiProvider.ts`

- Issue count: **7** (7 errors, 0 warnings)

1. **ERROR** at `117:39` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
2. **ERROR** at `118:36` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
3. **ERROR** at `124:36` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
4. **ERROR** at `177:33` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
5. **ERROR** at `179:32` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
6. **ERROR** at `217:39` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.
7. **ERROR** at `218:36` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/services/templates/apiVariableExtractor.ts`

- Issue count: **1** (1 errors, 0 warnings)

1. **ERROR** at `44:39` - `@typescript-eslint/no-explicit-any`
   - Issue: Unexpected any. Specify a different type.
   - Likely fix: Replace `any` with concrete domain types. If shape is unknown, use `unknown` and narrow with type guards, or define reusable interfaces/types in `src/types/`.

### `src/utils/evalFormatters.ts`

- Issue count: **1** (0 errors, 1 warnings)

1. **WARNING** at `76:1` - `(no-rule)`
   - Issue: Unused eslint-disable directive (no problems were reported from '@typescript-eslint/no-explicit-any').
   - Likely fix: Remove stale `eslint-disable` comments or scope them to active rules only.
