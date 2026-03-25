# AI Evals Platform — Education App Rebuild Plan

## Problem

`docs/guide/index.html` is a 5000-line, 166KB monolithic HTML file containing the full interactive guide (7 tabs, D3 brain map, mermaid diagrams, code blocks, tables, theme toggle). It works but doesn't scale — can't add pages, can't share individual sections, hard to maintain, and content drifts from the actual codebase.

## Goal

Rebuild as a standalone mini Vite + React app inside `docs/guide/` that:

1. Preserves all existing content and interactivity
2. Splits content into modular page components
3. Matches the main app's design philosophy (Tailwind v4, lucide-react, same fonts/tokens)
4. Supports per-page PDF/HTML export for team sharing
5. Includes a simple data-sync pipeline so `npm run build` reflects the latest codebase state

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Build | Vite + React 19 + TypeScript | Mirrors main app, fast, familiar |
| Styling | Tailwind CSS v4 + CSS variables | Same design tokens as main app |
| Icons | lucide-react | Same as main app |
| Diagrams | mermaid (ESM import) | Already used, renders flowcharts/ER/sequence |
| Brain Map | D3.js v7 | Already used for force-directed graph |
| Code blocks | Prism.js or shiki | Syntax highlighting with copy button |
| Routing | Hash-based (no server needed) | Simple, works with `file://` and static hosting |
| Export | window.print() + @media print CSS | Zero-dependency, works for both PDF and paper |

## Project Structure

```
docs/guide/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── scripts/
│   └── sync-data.ts          # Prebuild: extract data from main app source
├── src/
│   ├── main.tsx
│   ├── App.tsx                # Layout + hash router
│   ├── app.css                # Tailwind base + design tokens + print styles
│   ├── components/
│   │   ├── Layout.tsx         # Header, nav tabs, theme toggle, footer
│   │   ├── CodeBlock.tsx      # Syntax highlight + copy button
│   │   ├── MermaidDiagram.tsx # Renders mermaid markup, re-renders on theme change
│   │   ├── DataTable.tsx      # Reusable table with optional badges
│   │   ├── Card.tsx           # Surface card (hover lift)
│   │   ├── Accordion.tsx      # Collapsible section
│   │   ├── StepperFlow.tsx    # Numbered step visualization
│   │   ├── FilterPills.tsx    # Pill toggle group
│   │   └── ExportButton.tsx   # Per-page "Export PDF" / "Export HTML" button
│   ├── pages/
│   │   ├── Overview.tsx       # Hero + workspaces + tech stack + arch diagram
│   │   ├── Workflows.tsx      # Universal pattern + per-workspace accordions
│   │   ├── ApiAuth.tsx        # LLM providers + credentials + model discovery
│   │   ├── PromptsSchemas.tsx # Variable registry table + schema systems + examples
│   │   ├── Pipelines.tsx      # 5 pipeline views with filter pills
│   │   ├── BrainMap.tsx       # D3 force graph + search + filters + info panel
│   │   └── DbApiRef.tsx       # DB models table + ER diagram + API routes table
│   ├── data/
│   │   ├── navigation.ts      # Tab definitions (id, label, icon)
│   │   ├── brainMap.ts        # Node + link definitions for D3 graph
│   │   ├── templateVars.ts    # Variable registry rows (synced from source)
│   │   ├── dbModels.ts        # Database model definitions (synced from source)
│   │   └── apiRoutes.ts       # API route definitions (synced from source)
│   └── hooks/
│       ├── useTheme.ts        # Dark/light toggle, persists to localStorage
│       └── usePageExport.ts   # Triggers print or HTML snapshot
```

## Content Mapping (Old → New)

| Old HTML Section | New Module | Content Source |
|-----------------|------------|---------------|
| Tab 1: Overview | `pages/Overview.tsx` | Static (hero, workspace cards, tech stack, arch mermaid) |
| Tab 2: Workflows | `pages/Workflows.tsx` | Static (stepper, 3 accordion sections with mermaid) |
| Tab 3: API & Auth | `pages/ApiAuth.tsx` | Static (provider cards, credential flow mermaid) |
| Tab 4: Prompts & Schemas | `pages/PromptsSchemas.tsx` | `data/templateVars.ts` (synced) + static schema examples |
| Tab 5: Pipelines | `pages/Pipelines.tsx` | Static (5 pipeline mermaid diagrams with pill toggle) |
| Tab 6: Brain Map | `pages/BrainMap.tsx` | `data/brainMap.ts` (synced) |
| Tab 7: DB & API Ref | `pages/DbApiRef.tsx` | `data/dbModels.ts` + `data/apiRoutes.ts` (synced) + ER mermaid |

## Data Sync Pipeline

A lightweight prebuild script (`scripts/sync-data.ts`) runs before `vite build`:

```json
{
  "scripts": {
    "sync": "tsx scripts/sync-data.ts",
    "dev": "npm run sync && vite",
    "build": "npm run sync && tsc -b && vite build"
  }
}
```

What it extracts (reads source files, outputs TypeScript data files):

| Source | Target | Method |
|--------|--------|--------|
| `src/services/templates/variableRegistry.ts` | `data/templateVars.ts` | Parse VARIABLE_REGISTRY array |
| `backend/app/models/*.py` | `data/dbModels.ts` | Parse class names + `__tablename__` + column defs |
| `backend/app/main.py` | `data/apiRoutes.ts` | Parse `app.include_router()` calls + route prefixes |
| `backend/app/services/evaluators/*.py` + `src/features/**/*.tsx` | `data/brainMap.ts` | Parse file paths + exported functions/classes |

If sync fails (e.g., source files moved), build still works — data files have committed fallback values.

## Export Strategy

### Per-Page PDF Export
- `ExportButton` component renders a print icon button on each page header
- Click triggers `window.print()` with page-specific title
- `@media print` CSS: hides nav/header/footer, forces white background, page-break rules
- Users save as PDF from browser print dialog (universal, zero-dependency)

### Per-Page HTML Export
- `ExportButton` offers "Copy as HTML" option
- Captures the current page's rendered HTML, wraps it with inline styles + the design tokens
- Copies to clipboard or triggers download as `.html` file
- Self-contained single-file output (all styles inlined, mermaid rendered as SVG)

## Design Tokens (Matching Main App)

Reuse the exact same CSS variables from the existing guide:

```css
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --text: #0f172a;
  --text-secondary: #475569;
  --accent: #6366f1;
  --border: #e2e8f0;
  /* ... same tokens as current guide */
}
[data-theme="dark"] { /* dark overrides */ }
```

Tailwind v4 configured to use these tokens so utility classes work naturally.

## Implementation Phases

### Phase 1: Scaffold + Layout (foundation)
- Init Vite + React + TS project in `docs/guide/`
- Tailwind v4 setup with design tokens
- `Layout` component: header (logo + title + badge + theme toggle), nav tabs, content area, footer
- `useTheme` hook with localStorage persistence
- Hash-based routing between 7 pages
- Empty page shells for all 7 sections

### Phase 2: Shared Components
- `CodeBlock` (Prism highlighting + copy)
- `MermaidDiagram` (render + theme-aware re-render)
- `DataTable`, `Card`, `Accordion`, `StepperFlow`, `FilterPills`
- `ExportButton` with print + HTML download

### Phase 3: Content Pages (port content from HTML)
- Port each tab's content into its page component
- Use shared components for tables, diagrams, code blocks
- Extract data arrays (brain map nodes, variable registry, db models, api routes) into `data/` files

### Phase 4: Brain Map
- Port D3 force graph into React component
- Feature pill filtering, layer filtering, search, click-to-info-panel
- Data sourced from `data/brainMap.ts`

### Phase 5: Data Sync + Export
- Write `scripts/sync-data.ts` prebuild script
- Wire into `npm run dev` and `npm run build`
- Finalize `@media print` CSS
- HTML export utility

## What This Does NOT Include (Keep Simple)
- No SSR or server rendering
- No database or backend
- No auth
- No complex state management (just useState/useTheme)
- No testing framework (manual verification only)
- No CI/CD pipeline (local dev only)
- No MDX or markdown-based content (JSX is simpler for this interactive content)
