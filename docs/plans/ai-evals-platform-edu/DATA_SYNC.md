# Data Sync Pipeline

How content stays in sync with the main codebase.

## Overview

A prebuild script (`scripts/sync-data.ts`) runs before `vite dev` and `vite build`. It reads source files from the main app (`../../src/` and `../../backend/`) and generates TypeScript data files in `src/data/`.

```
npm run sync → reads main app source → writes src/data/*.ts → vite builds from those files
```

## What Gets Synced

### 1. Template Variables (`data/templateVars.ts`)

**Source:** `../../src/services/templates/variableRegistry.ts`
**Method:** Parse the `VARIABLE_REGISTRY` array export
**Output:**
```ts
export const templateVariables = [
  { name: '{{audio}}', type: 'file', description: '...', apps: ['voice-rx'], promptTypes: [...], flows: [...] },
  // ...
];
```

### 2. Database Models (`data/dbModels.ts`)

**Source:** `../../backend/app/models/*.py`
**Method:** Parse each SQLAlchemy model file for:
- Class name (e.g., `class EvalRun`)
- `__tablename__` value
- `Column()` definitions (name, type, FK references)
**Output:**
```ts
export const dbModels = [
  { model: 'EvalRun', table: 'eval_runs', columns: [...], description: '...' },
  // ...
];
```

### 3. API Routes (`data/apiRoutes.ts`)

**Source:** `../../backend/app/main.py` + `../../backend/app/routes/*.py`
**Method:**
- Parse `app.include_router()` calls from main.py for prefix mapping
- Parse route files for `@router.get/post/put/delete` decorators
**Output:**
```ts
export const apiRoutes = [
  { router: 'listings', prefix: '/api/listings', endpoints: [...], description: '...' },
  // ...
];
```

### 4. Brain Map Nodes (`data/brainMap.ts`)

**Source:** `../../backend/app/services/evaluators/*.py` + `../../src/features/**/*.{ts,tsx}`
**Method:**
- Scan evaluator files for class/function definitions
- Scan frontend feature files for exported components/hooks
- Group by feature (voice-rx-eval, batch-eval, adversarial, custom-evaluators, template-vars, llm-pipeline, settings-config)
**Output:**
```ts
export const brainMapNodes = [...];
export const brainMapLinks = [...];
```

## Fallback Strategy

Each data file has a committed baseline (the current content from the HTML guide). If sync fails:
- Script logs a warning but does not fail the build
- Vite uses the existing committed data files
- Manual edits to data files are preserved (sync only overwrites if it can fully parse)

## Script Implementation

```ts
// scripts/sync-data.ts
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve } from 'path';

const ROOT = resolve(__dirname, '../../../');  // main app root
const DATA_DIR = resolve(__dirname, '../src/data');

function syncTemplateVars() { /* ... */ }
function syncDbModels() { /* ... */ }
function syncApiRoutes() { /* ... */ }
function syncBrainMap() { /* ... */ }

try {
  syncTemplateVars();
  syncDbModels();
  syncApiRoutes();
  syncBrainMap();
  console.log('[sync] Data files updated');
} catch (err) {
  console.warn('[sync] Partial sync — using committed fallback:', err.message);
}
```

## Running

```bash
cd docs/guide
npm run sync       # Manual sync only
npm run dev        # Sync + dev server
npm run build      # Sync + production build
```
