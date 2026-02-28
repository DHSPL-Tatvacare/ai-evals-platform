import { cn } from '@/utils/cn';
import { PRIORITY_STYLES } from './colors';

interface Props {
  priority: 'P0' | 'P1' | 'P2';
  className?: string;
}

export default function PriorityBadge({ priority, className }: Props) {
  const style = PRIORITY_STYLES[priority];
  return (
    <span className={cn(
      'inline-block px-2 py-0.5 text-xs font-semibold rounded-full',
      style.bg,
      style.text,
      className,
    )}>
      {style.label}
    </span>
  );
}
