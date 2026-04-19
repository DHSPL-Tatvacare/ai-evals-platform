/**
 * Display formatters shared across the cost dashboard.
 *
 * `formatUsd` returns `$1,234.56` / `$0.0012` depending on magnitude.
 * `formatTokens` groups thousands; `formatTokensCompact` uses k/M suffixes
 * suitable for chips and badges.
 */

export function formatUsd(value: number): string {
  if (!Number.isFinite(value)) return '$0';
  const abs = Math.abs(value);
  if (abs === 0) return '$0';
  if (abs < 0.01) return `$${value.toFixed(4)}`;
  if (abs < 1) return `$${value.toFixed(3)}`;
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatUsdCompact(value: number): string {
  if (!Number.isFinite(value)) return '$0';
  const abs = Math.abs(value);
  if (abs < 0.01 && abs > 0) return `<$0.01`;
  if (abs >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  return `$${value.toFixed(2)}`;
}

export function formatTokens(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString('en-US') : '0';
}

export function formatTokensCompact(value: number): string {
  if (!Number.isFinite(value) || value === 0) return '0';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toString();
}

export function formatInt(value: number): string {
  return Number.isFinite(value) ? Math.trunc(value).toLocaleString('en-US') : '0';
}

export function formatPercent(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '0%';
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('en-US', {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function truncateId(id: string | null | undefined, head = 6): string {
  if (!id) return '—';
  if (id.length <= head + 4) return id;
  return `${id.slice(0, head)}…${id.slice(-4)}`;
}
