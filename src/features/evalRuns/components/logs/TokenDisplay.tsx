interface TokenDisplayProps {
  tokensIn?: number | null;
  tokensOut?: number | null;
}

function formatCount(n: number): string {
  return n.toLocaleString();
}

export function TokenDisplay({ tokensIn, tokensOut }: TokenDisplayProps) {
  if (tokensIn == null && tokensOut == null) return null;

  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
      {tokensIn != null && (
        <span title="Tokens in">
          <span className="text-[var(--text-tertiary)]">&uarr;</span> {formatCount(tokensIn)}
        </span>
      )}
      {tokensIn != null && tokensOut != null && (
        <span className="text-[var(--text-tertiary)]">&middot;</span>
      )}
      {tokensOut != null && (
        <span title="Tokens out">
          <span className="text-[var(--text-tertiary)]">&darr;</span> {formatCount(tokensOut)}
        </span>
      )}
    </span>
  );
}
