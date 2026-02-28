import { useState, useRef, useCallback, type ReactNode } from 'react';
import { Info } from 'lucide-react';

interface Props {
  title: string;
  description?: string;
  infoTooltip?: ReactNode;
}

export default function SectionHeader({ title, description, infoTooltip }: Props) {
  return (
    <div className="mb-6 pb-3 border-b border-[var(--border-subtle)]">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-bold uppercase tracking-wider text-[var(--text-primary)]">
          {title}
        </h2>
        {infoTooltip && <InfoHover content={infoTooltip} />}
      </div>
      {description && (
        <p className="text-xs text-[var(--text-muted)] mt-1">{description}</p>
      )}
    </div>
  );
}

function InfoHover({ content }: { content: ReactNode }) {
  const [visible, setVisible] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const show = useCallback(() => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    setVisible(true);
  }, []);

  const hide = useCallback(() => {
    hideTimer.current = setTimeout(() => setVisible(false), 150);
  }, []);

  return (
    <div
      className="relative inline-flex print:hidden"
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <span
        className="p-0.5 rounded-full text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors cursor-help"
        aria-label="Section info"
      >
        <Info className="h-3.5 w-3.5" />
      </span>
      {visible && (
        <div
          className="absolute left-0 top-full mt-1 w-[340px] max-h-[400px] overflow-y-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg z-30 p-3 text-xs leading-relaxed text-[var(--text-secondary)]"
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          {content}
        </div>
      )}
    </div>
  );
}
