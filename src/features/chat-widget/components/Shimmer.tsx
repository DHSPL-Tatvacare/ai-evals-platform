import { cn } from '@/utils/cn';

interface ShimmerProps {
  children: React.ReactNode;
  className?: string;
}

export function Shimmer({ children, className }: ShimmerProps) {
  return (
    <span
      className={cn(
        'bg-[linear-gradient(90deg,var(--text-muted),var(--text-primary),var(--text-muted))] bg-[length:200%_100%] bg-clip-text text-transparent animate-[chat-widget-shimmer_1.6s_linear_infinite]',
        className,
      )}
    >
      {children}
    </span>
  );
}
