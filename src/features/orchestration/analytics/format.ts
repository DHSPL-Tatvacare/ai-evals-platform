/** Local formatters for the orchestration analytics surface. Kept feature-local
 *  so the surface doesn't import cost-coupled helpers. */

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

// Cost is stored and reported in USD platform-wide; this formatter assumes USD.
export function formatUsd(value: number): string {
  return USD.format(Number.isFinite(value) ? value : 0);
}

export function formatInt(value: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(Number.isFinite(value) ? value : 0));
}

/** Percentage of `value` over `total`, rendered as e.g. "25%". */
export function formatPct(value: number, total: number): string {
  if (!total) return '0%';
  return `${Math.round((value / total) * 100)}%`;
}
