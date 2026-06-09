import { cn } from '@/utils';

export type IllustrationKey = 'error' | 'empty' | 'notFound' | 'welcome';

const SOURCES: Record<IllustrationKey, string> = {
  error: '/illustrations/error.webp',
  empty: '/illustrations/empty.webp',
  notFound: '/illustrations/not-found.webp',
  welcome: '/illustrations/welcome.webp',
};

interface IllustrationProps {
  name: IllustrationKey;
  className?: string;
}

export function Illustration({ name, className }: IllustrationProps) {
  return (
    <img
      src={SOURCES[name]}
      alt=""
      aria-hidden="true"
      draggable={false}
      className={cn('select-none', className)}
    />
  );
}
