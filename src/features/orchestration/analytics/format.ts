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

/** Seconds rendered as a compact talk-time string, e.g. 95 -> "1m 35s", 42 -> "42s". */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(Number.isFinite(totalSeconds) ? totalSeconds : 0));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}
