import type { ElementType } from 'react';
import { AlertCircle, CheckCircle2, FileSpreadsheet } from 'lucide-react';

import { cn } from '@/utils';

type FileInfoVariant = 'success' | 'error' | 'warning' | 'neutral';

const FILE_BAR_STYLES: Record<FileInfoVariant, { bg: string; border: string; icon: ElementType; iconColor: string }> = {
  success: { bg: 'bg-[var(--surface-success)]', border: 'border-[var(--border-success)]', icon: CheckCircle2, iconColor: 'text-[var(--color-success)]' },
  error: { bg: 'bg-[var(--surface-error)]', border: 'border-[var(--border-error)]', icon: AlertCircle, iconColor: 'text-[var(--color-error)]' },
  warning: { bg: 'bg-[var(--color-warning-light)]', border: 'border-[var(--color-warning)]/30', icon: AlertCircle, iconColor: 'text-[var(--color-warning)]' },
  neutral: { bg: 'bg-[var(--bg-secondary)]', border: 'border-[var(--border-subtle)]', icon: FileSpreadsheet, iconColor: 'text-[var(--text-muted)]' },
};

interface CsvFileInfoBarProps {
  file: File;
  variant: FileInfoVariant;
  onReset: () => void;
}

export function CsvFileInfoBar({ file, variant, onReset }: CsvFileInfoBarProps) {
  const style = FILE_BAR_STYLES[variant];
  const Icon = style.icon;

  return (
    <div className={cn('flex items-center justify-between px-4 py-3 rounded-[6px]', style.bg, 'border', style.border)}>
      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4', style.iconColor)} />
        <span className="text-[13px] font-medium text-[var(--text-primary)]">{file.name}</span>
        <span className="text-[11px] text-[var(--text-muted)]">
          ({(file.size / 1024).toFixed(1)} KB)
        </span>
      </div>
      <button
        onClick={onReset}
        className="text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors underline"
      >
        Change file
      </button>
    </div>
  );
}
