import { useRef } from 'react';

export function usePageExport() {
  const contentRef = useRef<HTMLDivElement>(null);
  return { contentRef } as const;
}
