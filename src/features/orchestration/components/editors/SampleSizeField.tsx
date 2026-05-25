import { NumberPresetSelect } from '@/components/ui/NumberPresetSelect';
import { Select } from '@/components/ui/Select';
import { InspectorField } from '@/features/orchestration/components/inspector/InspectorPrimitives';

type Strategy = 'random' | 'first';

interface Props {
  limit: number | null;
  strategy: Strategy;
  onChange: (next: { limit: number | null; strategy: Strategy }) => void;
}

const PRESETS = [10, 100, 1000, 10000];

const STRATEGY_OPTIONS = [
  { value: 'none', label: 'No limit' },
  { value: 'random', label: 'Random sample' },
  { value: 'first', label: 'First N' },
];

export function SampleSizeField({ limit, strategy, onChange }: Props) {
  const strategyValue = limit == null ? 'none' : strategy;

  function setStrategy(next: string) {
    if (next === 'none') {
      onChange({ limit: null, strategy });
      return;
    }
    // Picking a strategy with no size yet defaults to 100.
    onChange({ limit: limit ?? 100, strategy: next as Strategy });
  }

  function setSize(n: number) {
    onChange({ limit: n, strategy });
  }

  return (
    <InspectorField
      label="Sample size"
      description="Cap this run to a fixed number of contacts. The rest are left untouched."
    >
      <Select
        value={strategyValue}
        onChange={setStrategy}
        options={STRATEGY_OPTIONS}
      />
      {limit != null ? (
        <NumberPresetSelect
          value={limit}
          onChange={setSize}
          presets={PRESETS}
          min={1}
          max={10000}
        />
      ) : null}
    </InspectorField>
  );
}
