/**
 * Radix reserves `''` as the Item value that clears the selection, so it
 * throws if any `<Select.Item value="">` is rendered. Callers legitimately use
 * `''` as an "All / Any" option, so `Select` swaps it for this sentinel at the
 * Radix boundary and swaps back on change — keeping `''` valid everywhere.
 */
export const EMPTY_OPTION_VALUE = '__select_empty_option__';

export const toRadixValue = (value: string): string =>
  value === '' ? EMPTY_OPTION_VALUE : value;

export const fromRadixValue = (value: string): string =>
  value === EMPTY_OPTION_VALUE ? '' : value;
