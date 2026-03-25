export function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

export function formatDateTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/** Format a First Response Time (seconds) with colour semantics: green ≤1h, amber 1–3h, red >3h. */
export function formatFrt(seconds: number | null): { text: string; color: string } {
  if (seconds === null) return { text: '—', color: '' };
  if (seconds <= 3600) {
    return { text: seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m`, color: 'text-emerald-400' };
  }
  if (seconds <= 10800) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return { text: m > 0 ? `${h}h ${m}m` : `${h}h`, color: 'text-amber-400' };
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return { text: m > 0 ? `${h}h ${m}m` : `${h}h`, color: 'text-red-400' };
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function generateId(): string {
  return crypto.randomUUID();
}
