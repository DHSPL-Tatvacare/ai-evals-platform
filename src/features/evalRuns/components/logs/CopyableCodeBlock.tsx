import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/utils';

interface CopyableCodeBlockProps {
  content: string;
  label?: string;
  labelColor?: string;
  variant?: 'default' | 'success' | 'error';
  maxHeight?: string;
}

const variantStyles: Record<string, { bg: string; border: string; text?: string }> = {
  default: { bg: 'bg-[var(--bg-secondary)]', border: 'border-[var(--border-subtle)]' },
  success: { bg: 'bg-[var(--surface-success)]', border: 'border-[var(--border-success)]' },
  error: { bg: 'bg-[var(--surface-error)]', border: 'border-[var(--border-error)]', text: 'text-[var(--color-error)]' },
};

export function CopyableCodeBlock({
  content,
  label,
  labelColor,
  variant = 'default',
  maxHeight = 'max-h-64',
}: CopyableCodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [content]);

  const styles = variantStyles[variant];

  return (
    <div>
      {label && (
        <p
          className="text-xs uppercase tracking-wider font-semibold mb-1"
          style={{ color: labelColor }}
        >
          {label}
        </p>
      )}
      <div className="relative group">
        <pre
          className={cn(
            styles.bg,
            'border',
            styles.border,
            'rounded p-2.5 text-xs whitespace-pre-wrap overflow-y-auto',
            styles.text || 'text-[var(--text-primary)]',
            maxHeight,
          )}
        >
          {content}
        </pre>
        <button
          onClick={handleCopy}
          className="absolute top-1.5 right-1.5 p-1 rounded bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--text-primary)] opacity-0 group-hover:opacity-100 transition-opacity"
          title="Copy to clipboard"
        >
          {copied ? <Check className="h-3 w-3 text-[var(--color-success)]" /> : <Copy className="h-3 w-3" />}
        </button>
      </div>
    </div>
  );
}
