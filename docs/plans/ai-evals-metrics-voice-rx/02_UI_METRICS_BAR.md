# 02 — MetricsBar & MetricCard UI Changes

## Files involved

| File | Action |
|---|---|
| `src/features/evals/components/MetricsBar.tsx` | Flow-aware rendering (3 vs 5 cards) |
| `src/features/evals/components/MetricCard.tsx` | No changes needed (already generic) |

---

## 1. `MetricsBar.tsx` — Flow-aware rendering

### Current code

```typescript
export function MetricsBar({ metrics }: MetricsBarProps) {
  // ... null state ...

  return (
    <div className="mt-3 flex items-center gap-3">
      <div className="grid grid-cols-3 gap-2" style={{ minWidth: '360px' }}>
        <MetricCard metric={metrics.match} compact />
        <MetricCard metric={metrics.wer} compact />
        <MetricCard metric={metrics.cer} compact />
      </div>
    </div>
  );
}
```

Hard-codes 3 columns and accesses `metrics.match` which is now optional for API flow.

### Proposed: Branch on `flowType`

```typescript
import { Sparkles } from 'lucide-react';
import { MetricCard } from './MetricCard';
import type { ListingMetrics } from '../metrics';

interface MetricsBarProps {
  metrics: ListingMetrics | null;
}

export function MetricsBar({ metrics }: MetricsBarProps) {
  if (!metrics) {
    return (
      <div className="mt-3 flex items-center gap-2">
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
          <Sparkles className="h-4 w-4 text-[var(--text-muted)]" />
          <span className="text-[12px] text-[var(--text-muted)]">
            Run AI Evaluation to see metrics
          </span>
        </div>
      </div>
    );
  }

  if (metrics.flowType === 'api') {
    // API flow: Field Accuracy, Recall, Precision, WER, CER
    return (
      <div className="mt-3 flex items-center gap-3">
        <div className="grid grid-cols-5 gap-2" style={{ minWidth: '600px' }}>
          {metrics.fieldAccuracy && <MetricCard metric={metrics.fieldAccuracy} compact />}
          {metrics.extractionRecall && <MetricCard metric={metrics.extractionRecall} compact />}
          {metrics.extractionPrecision && <MetricCard metric={metrics.extractionPrecision} compact />}
          <MetricCard metric={metrics.wer} compact />
          <MetricCard metric={metrics.cer} compact />
        </div>
      </div>
    );
  }

  // Upload flow: Match, WER, CER (unchanged)
  return (
    <div className="mt-3 flex items-center gap-3">
      <div className="grid grid-cols-3 gap-2" style={{ minWidth: '360px' }}>
        {metrics.match && <MetricCard metric={metrics.match} compact />}
        <MetricCard metric={metrics.wer} compact />
        <MetricCard metric={metrics.cer} compact />
      </div>
    </div>
  );
}
```

### Layout for API flow

```
┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│ Field       │ Recall      │ Precision   │ WER         │ CER         │
│ Accuracy    │             │             │             │             │
│   29.0%     │   71.0%     │   40.9%     │   0.42      │   0.38      │
│ ████░░░░░░  │ ███████░░░  │ ████░░░░░░  │ ██████░░░░  │ ██████░░░░  │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

### Layout for Upload flow (unchanged)

```
┌──────────────┬──────────────┬──────────────┐
│ Match        │ WER          │ CER          │
│   95.0%      │   0.05       │   0.03       │
│ █████████░   │ █████████░   │ ██████████   │
└──────────────┴──────────────┴──────────────┘
```

---

## 2. `MetricCard.tsx` — No changes required

`MetricCard` is already fully generic. It renders from a `MetricResult` object:

```typescript
interface MetricCardProps {
  metric: MetricResult;
  compact?: boolean;
}
```

All display values come from the `MetricResult` shape:
- `metric.label` — "Field Accuracy", "Recall", etc.
- `metric.displayValue` — "29.0%", "0.42", etc.
- `metric.percentage` — drives the progress bar width
- `metric.rating` — drives the color via `getRatingColors()`

No changes needed here. The new metrics (fieldAccuracy, extractionRecall, extractionPrecision) all produce valid `MetricResult` objects as defined in `01_TYPES_AND_COMPUTATION.md`.

---

## 3. Grid column count

The `grid-cols-5` for API flow fits the page because:
- Current page width has plenty of space (MetricsBar is inside a container with sidebar)
- `minWidth: '600px'` ensures cards don't compress below readable size (120px each)
- Each MetricCard in compact mode is ~120px wide minimum

If 5 columns feels cramped, alternative: use `grid-cols-3` with two rows:
```
Row 1: Field Accuracy | Recall | Precision
Row 2: WER | CER | (empty)
```

This can be decided at implementation time based on visual result.

---

## 4. WER/CER percentage bar direction

For WER and CER, the bar represents "accuracy" (1 - errorRate), so:
- WER 0.05 → bar shows 95% (mostly full, green)
- WER 0.42 → bar shows 58% (half full, yellow/fair)
- WER 0.95 → bar shows 5% (almost empty, red)

This is already handled by `calculateWERMetric` and `calculateCERMetric` which set `percentage = (1 - wer) * 100`.

---

## 5. Cross-script warning (optional enhancement)

When normalization is OFF and the API transcript is in a different script than the judge transcript, WER/CER will be near 100%. Consider adding a small warning tooltip or badge on the WER/CER cards when `metrics.flowType === 'api'` and normalization was disabled.

Data source: `aiEval.normalizationMeta.enabled` (available in the hook).

This is optional and can be deferred — the WER/CER values themselves are correct, just potentially uninformative for cross-script comparisons.
