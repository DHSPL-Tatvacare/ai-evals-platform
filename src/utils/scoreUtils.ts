/** Color for a 0–100 overall score. */
export function scoreColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)';
  if (score >= 80) return 'var(--color-success)';
  if (score >= 65) return 'var(--color-warning)';
  return 'var(--color-error)';
}

/** Text band label for a 0–100 overall score. */
export function getScoreBand(score: number | null): string {
  if (score === null) return 'Unknown';
  if (score >= 80) return 'Strong';
  if (score >= 65) return 'Good';
  if (score >= 50) return 'Needs work';
  return 'Poor';
}
