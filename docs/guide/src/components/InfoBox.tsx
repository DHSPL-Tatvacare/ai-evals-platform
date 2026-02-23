import type { ReactNode } from 'react';
import { Info } from 'lucide-react';

interface InfoBoxProps {
  children: ReactNode;
  className?: string;
}

export default function InfoBox({ children, className = '' }: InfoBoxProps) {
  return (
    <div
      className={`flex gap-3 rounded-lg p-4 ${className}`}
      style={{
        background: 'var(--info-bg)',
        borderLeft: '4px solid var(--info-border)',
      }}
    >
      <Info
        size={20}
        className="flex-shrink-0 mt-0.5"
        style={{ color: 'var(--info)' }}
      />
      <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        {children}
      </div>
    </div>
  );
}
