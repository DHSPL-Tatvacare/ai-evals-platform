import type { ReactNode } from 'react';

const colorStyles: Record<string, { bg: string; text: string; darkBg: string; darkText: string }> = {
  blue: { bg: '#dbeafe', text: '#1e40af', darkBg: '#1e3a5f', darkText: '#93c5fd' },
  green: { bg: '#dcfce7', text: '#166534', darkBg: '#14532d', darkText: '#86efac' },
  purple: { bg: '#f3e8ff', text: '#6b21a8', darkBg: '#3b0764', darkText: '#d8b4fe' },
  amber: { bg: '#fef3c7', text: '#92400e', darkBg: '#78350f', darkText: '#fcd34d' },
  red: { bg: '#fee2e2', text: '#991b1b', darkBg: '#7f1d1d', darkText: '#fca5a5' },
};

interface BadgeProps {
  color: 'blue' | 'green' | 'purple' | 'amber' | 'red';
  children: ReactNode;
}

export default function Badge({ color, children }: BadgeProps) {
  const style = colorStyles[color];
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
      style={{ background: `var(--badge-bg-${color}, ${style.bg})`, color: `var(--badge-text-${color}, ${style.text})` }}
    >
      <style>{`
        [data-theme="dark"] {
          --badge-bg-${color}: ${style.darkBg};
          --badge-text-${color}: ${style.darkText};
        }
      `}</style>
      {children}
    </span>
  );
}
