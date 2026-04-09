import { cn } from '@/utils/cn';
import { getLabelDefinition } from '@/config/labelDefinitions';
import type { LabelCategory } from '@/config/labelDefinitions';

interface BeforeAfterChipProps {
  before: string;
  after: string;
  category?: LabelCategory;
  size?: 'sm' | 'md';
}

export function BeforeAfterChip({ before, after, category = 'correctness', size = 'sm' }: BeforeAfterChipProps) {
  const afterDef = getLabelDefinition(after, category);
  const textSize = size === 'sm' ? 'text-[9px]' : 'text-[10px]';
  const padding = size === 'sm' ? 'py-px px-1.5' : 'py-0.5 px-2';

  return (
    <span className={cn('inline-flex items-center rounded-full overflow-hidden border border-[var(--border-subtle)]', textSize, 'font-semibold')}>
      <span className={cn(padding, 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] line-through border-r border-[var(--border-subtle)]')}>
        {before}
      </span>
      <span className={cn(padding, 'text-white')} style={{ backgroundColor: afterDef.color }}>
        {after}
      </span>
    </span>
  );
}
