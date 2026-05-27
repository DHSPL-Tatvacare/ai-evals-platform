import { DateRangePicker } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';

const PRESETS = [
  { id: '24h', label: 'Last 24 hours' },
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
  { id: 'mtd', label: 'Month to date' },
];

const PRESET_IDS = new Set(PRESETS.map((p) => p.id));
const CUSTOM_RE = /^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$/;

export function CostFiltersBar() {
  const range = useCostStore((s) => s.filters.range);
  const setFilters = useCostStore((s) => s.setFilters);

  const activePreset = PRESET_IDS.has(range) ? range : null;
  const [from, to] = CUSTOM_RE.test(range) ? range.split(':') : [null, null];

  return (
    <div className="flex flex-wrap items-center gap-3">
      <DateRangePicker
        presets={PRESETS}
        activePreset={activePreset}
        from={from}
        to={to}
        onPresetSelect={(id) => setFilters({ range: id })}
        onCustomRange={(f, t) => setFilters({ range: `${f}:${t}` })}
      />
    </div>
  );
}
