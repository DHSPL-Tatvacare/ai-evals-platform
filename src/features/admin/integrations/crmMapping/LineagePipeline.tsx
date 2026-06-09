import { CheckCircle2, CircleDashed } from 'lucide-react';

import { cn } from '@/utils/cn';

import { type Stage } from './mappingStages';

export function LineagePipeline({ stages }: { stages: Stage[] }) {
  return (
    <ol className="flex items-center gap-2">
      {stages.map((s, i) => (
        <li key={s.key} className="flex items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center gap-1.5 text-[12px]',
              s.state === 'done' && 'text-[var(--text-primary)]',
              s.state === 'active' && 'font-medium text-[var(--text-brand)]',
              s.state === 'todo' && 'text-[var(--text-muted)]',
            )}
          >
            {s.state === 'done' ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-success)]" />
            ) : (
              <CircleDashed
                className={cn('h-3.5 w-3.5', s.state === 'active' ? 'text-[var(--text-brand)]' : 'text-[var(--text-muted)]')}
              />
            )}
            {s.label}
          </span>
          {i < stages.length - 1 ? <span className="h-px w-6 bg-[var(--border-default)]" aria-hidden /> : null}
        </li>
      ))}
    </ol>
  );
}
