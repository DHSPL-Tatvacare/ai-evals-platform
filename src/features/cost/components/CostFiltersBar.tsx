import { FilterPills } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';

const RANGE_OPTIONS = [
  { id: '24h', label: '24h' },
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
  { id: 'mtd', label: 'MTD' },
];

export function CostFiltersBar() {
  const range = useCostStore((s) => s.filters.range);
  const setFilters = useCostStore((s) => s.setFilters);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <FilterPills
        options={RANGE_OPTIONS}
        active={range}
        onChange={(id) => setFilters({ range: id })}
      />
    </div>
  );
}
