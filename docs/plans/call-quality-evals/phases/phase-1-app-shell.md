# Phase 1: Inside Sales — App Shell

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the Inside Sales app in the platform — app type, routes, sidebar, app switcher, and empty placeholder pages — so subsequent phases have a working shell to build into.

**Architecture:** Extend the existing multi-app architecture. Add `'inside-sales'` to the `AppId` union type, register routes under `/inside-sales/*`, create a nav-only sidebar (no scrollable item list), wire up the app switcher, and scaffold empty pages for all 5 sections.

**Tech Stack:** React, TypeScript, react-router-dom, Zustand, Tailwind CSS (via `cn()`), lucide-react icons.

**Branch:** `feat/phase-1-inside-sales-shell`

---

## Background

The platform currently supports two apps: `voice-rx` and `kaira-bot`. Each app has its own sidebar content, routes, and feature pages. The app architecture is driven by a single `AppId` type in `src/types/app.types.ts` — all consumers (stores, routes, sidebar, app switcher) derive from this.

Inside Sales is a nav-only app (no scrollable item list in the sidebar) with 5 sections: Listing, Evaluators, Runs, Dashboard, Logs. This phase creates the skeleton.

## Key files to reference

- `src/types/app.types.ts` — `AppId` type, `APPS` metadata record
- `src/config/routes.ts` — route definitions and helpers
- `src/app/Router.tsx` — route registration under `AuthGuard` + `MainLayout`
- `src/components/layout/AppSwitcher.tsx` — app dropdown list
- `src/components/layout/Sidebar.tsx` — conditional sidebar content rendering
- `src/components/layout/MainLayout.tsx` — app detection from pathname
- `src/components/layout/VoiceRxSidebarContent.tsx` — reference for sidebar nav link patterns
- `src/components/layout/KairaSidebarContent.tsx` — reference for sidebar nav link patterns

## Guidelines

- **No hardcoding.** All routes via `routes.ts` constants. All colors via CSS variables. All class merging via `cn()`.
- **Match existing patterns exactly.** Copy the structure from Voice Rx / Kaira, don't invent new patterns.
- **Empty pages use `EmptyState` component** with appropriate icons and messages.
- **App icon:** Create a simple phone icon SVG or use a placeholder image. The app switcher expects an icon path.

---

### Task 1: Extend AppId type and metadata

**Files:**
- Modify: `src/types/app.types.ts`

- [ ] **Step 1:** Read `src/types/app.types.ts` to understand the current `AppId` type and `APPS` record structure.

- [ ] **Step 2:** Add `'inside-sales'` to the `AppId` union type:

```typescript
export type AppId = 'voice-rx' | 'kaira-bot' | 'inside-sales';
```

- [ ] **Step 3:** Add Inside Sales entry to the `APPS` record:

```typescript
'inside-sales': {
  id: 'inside-sales',
  name: 'Inside Sales',
  icon: '/inside-sales-icon.svg',  // placeholder, will add actual icon
  description: 'Inside sales call quality evaluation',
  searchPlaceholder: 'Search calls...',
  newItemLabel: 'New Run',
},
```

- [ ] **Step 4:** Find and update any `Record<AppId, ...>` initializers in stores that hardcode the two existing apps. Search for `'voice-rx': []` and `'kaira-bot': []` patterns. Add `'inside-sales': []` to each. Key files to check:
  - `src/stores/listingsStore.ts`
  - `src/stores/evaluatorsStore.ts`
  - Any other store with `Record<AppId, T>` initialization

- [ ] **Step 5:** Add a placeholder icon file at `public/inside-sales-icon.svg`. Use a simple phone SVG:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#7030A0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
```

- [ ] **Step 6:** Run `npx tsc -b` to verify no type errors from the `AppId` change.

- [ ] **Step 7:** Commit:
```bash
git add src/types/app.types.ts public/inside-sales-icon.svg
# + any store files updated
git commit -m "feat: register inside-sales app type and metadata"
```

---

### Task 2: Add route definitions

**Files:**
- Modify: `src/config/routes.ts`

- [ ] **Step 1:** Read `src/config/routes.ts` to see the voice-rx and kaira route patterns.

- [ ] **Step 2:** Add the `insideSales` route object:

```typescript
insideSales: {
  home: '/inside-sales',
  listing: '/inside-sales',
  evaluators: '/inside-sales/evaluators',
  evaluatorDetail: (id: string) => `/inside-sales/evaluators/${id}`,
  runs: '/inside-sales/runs',
  runDetail: (runId: string) => `/inside-sales/runs/${runId}`,
  callDetail: (runId: string, callId: string) => `/inside-sales/runs/${runId}/calls/${callId}`,
  dashboard: '/inside-sales/dashboard',
  logs: '/inside-sales/logs',
  settings: '/inside-sales/settings',
},
```

- [ ] **Step 3:** Update the `runDetailForApp` helper to handle `'inside-sales'`:

```typescript
if (appId === 'inside-sales') return routes.insideSales.runDetail(runId);
```

- [ ] **Step 4:** Update `apiLogsForApp` similarly:

```typescript
if (appId === 'inside-sales') return routes.insideSales.logs;
```

- [ ] **Step 5:** Run `npx tsc -b` to verify.

- [ ] **Step 6:** Commit:
```bash
git add src/config/routes.ts
git commit -m "feat: add inside-sales route definitions"
```

---

### Task 3: Create InsideSalesSidebarContent

**Files:**
- Create: `src/components/layout/InsideSalesSidebarContent.tsx`

- [ ] **Step 1:** Read `src/components/layout/VoiceRxSidebarContent.tsx` for the nav link pattern (icon + label + active state using `useLocation` and `cn()`).

- [ ] **Step 2:** Create `InsideSalesSidebarContent.tsx`. This is **nav-only** — no search bar, no scrollable list, no item cards. Just 5 nav links:

```typescript
import { useLocation } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { LayoutGrid, FileText, GitCompareArrows, LayoutDashboard, ScrollText } from 'lucide-react';
import { cn } from '@/utils';
import { routes } from '@/config/routes';

const NAV_ITEMS = [
  { to: routes.insideSales.listing, icon: LayoutGrid, label: 'Listing' },
  { to: routes.insideSales.evaluators, icon: FileText, label: 'Evaluators' },
  { to: routes.insideSales.runs, icon: GitCompareArrows, label: 'Runs' },
  { to: routes.insideSales.dashboard, icon: LayoutDashboard, label: 'Dashboard' },
  { to: routes.insideSales.logs, icon: ScrollText, label: 'Logs' },
];

export function InsideSalesSidebarContent() {
  const location = useLocation();

  return (
    <nav className="flex flex-col gap-0.5 px-2 py-2">
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
        const isActive = location.pathname === to ||
          (to !== routes.insideSales.listing && location.pathname.startsWith(to));
        return (
          <Link
            key={to}
            to={to}
            className={cn(
              'flex items-center gap-2 rounded-[6px] px-3 py-2 text-[13px] font-medium transition-colors',
              isActive
                ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]'
            )}
          >
            <Icon className="h-[18px] w-[18px]" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 3:** Run `npx tsc -b`.

- [ ] **Step 4:** Commit:
```bash
git add src/components/layout/InsideSalesSidebarContent.tsx
git commit -m "feat: create nav-only sidebar for inside-sales"
```

---

### Task 4: Wire Sidebar and MainLayout

**Files:**
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/components/layout/MainLayout.tsx`
- Modify: `src/components/layout/AppSwitcher.tsx`

- [ ] **Step 1:** Read `Sidebar.tsx`. Find the conditional that switches between `VoiceRxSidebarContent` and `KairaSidebarContent`. Add an `'inside-sales'` case:

```typescript
import { InsideSalesSidebarContent } from './InsideSalesSidebarContent';

// In the render, find the conditional block and extend:
{appId === 'kaira-bot' ? (
  <KairaSidebarContent ... />
) : appId === 'inside-sales' ? (
  <InsideSalesSidebarContent />
) : (
  <VoiceRxSidebarContent ... />
)}
```

- [ ] **Step 2:** Read `MainLayout.tsx`. Find the pathname→app detection logic. Update it to detect `/inside-sales`:

```typescript
useEffect(() => {
  const isKairaRoute = location.pathname.startsWith('/kaira');
  const isInsideSalesRoute = location.pathname.startsWith('/inside-sales');
  const newApp = isInsideSalesRoute ? 'inside-sales' : isKairaRoute ? 'kaira-bot' : 'voice-rx';
  setCurrentApp(newApp);
  useMiniPlayerStore.getState().closeIfAppChanged(newApp);
}, [location.pathname, setCurrentApp]);
```

- [ ] **Step 3:** Read `AppSwitcher.tsx`. Add Inside Sales to the `apps` array:

```typescript
{
  id: 'inside-sales' as AppId,
  name: APPS['inside-sales'].name,
  icon: APPS['inside-sales'].icon,
  route: routes.insideSales.dashboard,
},
```

- [ ] **Step 4:** Also update the sidebar's `settingsPath` logic to handle inside-sales:

```typescript
const settingsPath = appId === 'kaira-bot'
  ? routes.kaira.settings
  : appId === 'inside-sales'
    ? routes.insideSales.settings
    : routes.voiceRx.settings;
```

- [ ] **Step 5:** Run `npx tsc -b` and `npm run lint`.

- [ ] **Step 6:** Commit:
```bash
git add src/components/layout/Sidebar.tsx src/components/layout/MainLayout.tsx src/components/layout/AppSwitcher.tsx
git commit -m "feat: wire inside-sales into sidebar, layout, and app switcher"
```

---

### Task 5: Create placeholder pages

**Files:**
- Create: `src/features/insideSales/pages/InsideSalesListing.tsx`
- Create: `src/features/insideSales/pages/InsideSalesEvaluators.tsx`
- Create: `src/features/insideSales/pages/InsideSalesRunList.tsx`
- Create: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`
- Create: `src/features/insideSales/pages/InsideSalesDashboard.tsx`
- Create: `src/features/insideSales/pages/index.ts`
- Create: `src/features/insideSales/index.ts`

- [ ] **Step 1:** Create the feature directory structure:

```
src/features/insideSales/
├── pages/
│   ├── InsideSalesListing.tsx
│   ├── InsideSalesEvaluators.tsx
│   ├── InsideSalesRunList.tsx
│   ├── InsideSalesRunDetail.tsx
│   ├── InsideSalesDashboard.tsx
│   └── index.ts
└── index.ts
```

- [ ] **Step 2:** Each placeholder page follows this pattern (adapt icon and text per page):

```typescript
// InsideSalesListing.tsx
import { LayoutGrid } from 'lucide-react';
import { EmptyState } from '@/components/ui';

export function InsideSalesListing() {
  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height))]">
      <div className="shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Calls</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          icon={LayoutGrid}
          title="Coming soon"
          description="The call listing will be built in Phase 2."
        />
      </div>
    </div>
  );
}
```

Create each page with appropriate icon and title:
- Listing: `LayoutGrid`, "Calls"
- Evaluators: `FileText`, "Evaluators"
- RunList: `GitCompareArrows`, "All Runs"
- RunDetail: `GitCompareArrows`, "Run Detail"
- Dashboard: `LayoutDashboard`, "Dashboard"

- [ ] **Step 3:** Create barrel exports:

```typescript
// src/features/insideSales/pages/index.ts
export { InsideSalesListing } from './InsideSalesListing';
export { InsideSalesEvaluators } from './InsideSalesEvaluators';
export { InsideSalesRunList } from './InsideSalesRunList';
export { InsideSalesRunDetail } from './InsideSalesRunDetail';
export { InsideSalesDashboard } from './InsideSalesDashboard';

// src/features/insideSales/index.ts
export * from './pages';
```

- [ ] **Step 4:** Run `npx tsc -b`.

- [ ] **Step 5:** Commit:
```bash
git add src/features/insideSales/
git commit -m "feat: scaffold inside-sales placeholder pages"
```

---

### Task 6: Register routes in Router.tsx

**Files:**
- Modify: `src/app/Router.tsx`

- [ ] **Step 1:** Read `Router.tsx`. Find where Voice Rx and Kaira routes are registered inside the `<AuthGuard><MainLayout /></AuthGuard>` block.

- [ ] **Step 2:** Import inside-sales pages and add the route block:

```typescript
import {
  InsideSalesListing,
  InsideSalesEvaluators,
  InsideSalesRunList,
  InsideSalesRunDetail,
  InsideSalesDashboard,
} from '@/features/insideSales';
```

Add routes inside the `MainLayout` Route element:

```typescript
{/* Inside Sales routes */}
<Route path={routes.insideSales.home} element={<Navigate to={routes.insideSales.dashboard} replace />} />
<Route path={routes.insideSales.listing} element={<InsideSalesListing />} />
<Route path={routes.insideSales.evaluators} element={<InsideSalesEvaluators />} />
<Route path="/inside-sales/evaluators/:id" element={<InsideSalesEvaluators />} />
<Route path={routes.insideSales.runs} element={<InsideSalesRunList />} />
<Route path="/inside-sales/runs/:runId" element={<InsideSalesRunDetail />} />
<Route path="/inside-sales/runs/:runId/calls/:callId" element={<InsideSalesRunDetail />} />
<Route path={routes.insideSales.dashboard} element={<InsideSalesDashboard />} />
<Route path={routes.insideSales.logs} element={<InsideSalesListing />} /> {/* Placeholder: reuse shared logs page later */}
<Route path={routes.insideSales.settings} element={<InsideSalesListing />} /> {/* Placeholder */}
```

Note: `home` redirects to `dashboard` (same pattern as Kaira). The `listing` route is the same as `home` path (`/inside-sales`) — revisit if this causes a redirect loop. If so, make home redirect to listing instead.

- [ ] **Step 3:** Run `npx tsc -b` and `npm run lint`.

- [ ] **Step 4:** Run `npm run dev` and manually verify:
  - App switcher shows "Inside Sales" with phone icon
  - Clicking it navigates to `/inside-sales/dashboard`
  - Sidebar shows 5 nav links, all clickable
  - Each page shows its placeholder EmptyState
  - Switching back to Voice Rx / Kaira works correctly

- [ ] **Step 5:** Commit:
```bash
git add src/app/Router.tsx
git commit -m "feat: register inside-sales routes in router"
```

---

### Task 7: Verify and merge

- [ ] **Step 1:** Run full checks:
```bash
npx tsc -b
npm run lint
npm run build
```

- [ ] **Step 2:** Manual smoke test:
  - Navigate to all 5 Inside Sales pages
  - Verify sidebar active state highlights correctly
  - Verify app switcher works in both directions (to and from Inside Sales)
  - Verify Voice Rx and Kaira still work (no regressions)

- [ ] **Step 3:** Merge to main:
```bash
git checkout main
git merge feat/phase-1-inside-sales-shell
```
