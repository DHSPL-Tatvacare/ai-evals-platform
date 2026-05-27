import { useState } from 'react';
import { DateRangeField, FilterPills } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';

const RANGE_OPTIONS = [
  { id: '24h', label: '24h' },
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
  { id: 'mtd', label: 'MTD' },
];

const CUSTOM_RE = /^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$/;

function parseCustomRange(range: string): { from: string; to: string } {
  if (CUSTOM_RE.test(range)) {
    const [from, to] = range.split(':');
    return { from, to };
  }
  return { from: '', to: '' };
}

export function CostFiltersBar() {
  const range = useCostStore((s) => s.filters.range);
  const setFilters = useCostStore((s) => s.setFilters);

  const initial = parseCustomRange(range);
  const [customFrom, setCustomFrom] = useState(initial.from);
  const [customTo, setCustomTo] = useState(initial.to);

  function handlePreset(id: string) {
    setCustomFrom('');
    setCustomTo('');
    setFilters({ range: id });
  }

  function handleFromChange(value: string) {
    setCustomFrom(value);
    if (value && customTo) {
      setFilters({ range: `${value}:${customTo}` });
    }
  }

  function handleToChange(value: string) {
    setCustomTo(value);
    if (customFrom && value) {
      setFilters({ range: `${customFrom}:${value}` });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <FilterPills options={RANGE_OPTIONS} active={range} onChange={handlePreset} />
      <span className="h-4 w-px shrink-0 bg-[var(--border-default)]" aria-hidden />
      <DateRangeField
        from={customFrom}
        to={customTo}
        onFromChange={handleFromChange}
        onToChange={handleToChange}
      />
    </div>
  );
}
