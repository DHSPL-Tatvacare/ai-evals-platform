import { useState, useRef, useEffect, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

interface AccordionProps {
  title: string;
  icon?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

export default function Accordion({ title, icon, defaultOpen = false, children }: AccordionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | undefined>(defaultOpen ? undefined : 0);

  useEffect(() => {
    if (!contentRef.current) return;
    if (isOpen) {
      setHeight(contentRef.current.scrollHeight);
      const timer = setTimeout(() => setHeight(undefined), 300);
      return () => clearTimeout(timer);
    } else {
      setHeight(contentRef.current.scrollHeight);
      requestAnimationFrame(() => setHeight(0));
    }
  }, [isOpen]);

  return (
    <div
      className="rounded-xl overflow-hidden my-3"
      style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}
    >
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center gap-3 px-5 py-4 text-left cursor-pointer transition-colors"
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--text)',
          fontFamily: 'inherit',
        }}
      >
        <ChevronRight
          size={18}
          className="transition-transform duration-200 shrink-0"
          style={{
            transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
            color: 'var(--accent-text)',
          }}
        />
        {icon && <span className="shrink-0" style={{ color: 'var(--accent-text)' }}>{icon}</span>}
        <span className="text-sm font-semibold">{title}</span>
      </button>
      <div
        ref={contentRef}
        className="overflow-hidden transition-[max-height] duration-300 ease-in-out"
        style={{ maxHeight: height === undefined ? 'none' : `${height}px` }}
      >
        <div className="px-5 pb-5">{children}</div>
      </div>
    </div>
  );
}
