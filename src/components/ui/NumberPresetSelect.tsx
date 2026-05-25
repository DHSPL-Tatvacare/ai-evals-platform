import { useState } from 'react';

import { Input } from './Input';
import { Select } from './Select';

const CUSTOM = '__custom__';

interface NumberPresetSelectProps {
  /** Current numeric value, or null when nothing is selected yet. */
  value: number | null;
  /** Fired with the resolved (clamped) number whenever it changes. */
  onChange: (value: number) => void;
  presets: number[];
  min?: number;
  max?: number;
  customLabel?: string;
  placeholder?: string;
}

export function NumberPresetSelect({
  value,
  onChange,
  presets,
  min = 1,
  max = Number.MAX_SAFE_INTEGER,
  customLabel = 'Custom…',
  placeholder = 'Select…',
}: NumberPresetSelectProps) {
  const valueIsPreset = value != null && presets.includes(value);
  // Custom mode is sticky once entered so a half-typed value doesn't snap back.
  const [customMode, setCustomMode] = useState(value != null && !valueIsPreset);

  const options = [
    ...presets.map((n) => ({ value: String(n), label: n.toLocaleString('en-US') })),
    { value: CUSTOM, label: customLabel },
  ];
  const selectValue = customMode ? CUSTOM : value != null ? String(value) : '';

  function clamp(n: number): number {
    return Math.max(min, Math.min(max, Math.trunc(n)));
  }

  function handleSelect(next: string) {
    if (next === CUSTOM) {
      setCustomMode(true);
      return;
    }
    setCustomMode(false);
    onChange(Number(next));
  }

  function handleCustom(raw: string) {
    const trimmed = raw.trim();
    if (trimmed === '') return;
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) return;
    onChange(clamp(parsed));
  }

  return (
    <div className="flex flex-col gap-2">
      <Select
        value={selectValue}
        onChange={handleSelect}
        options={options}
        placeholder={placeholder}
      />
      {customMode ? (
        <Input
          type="number"
          min={min}
          max={max}
          value={value == null ? '' : String(value)}
          onChange={(e) => handleCustom(e.target.value)}
          placeholder={`${min}–${max}`}
        />
      ) : null}
    </div>
  );
}
