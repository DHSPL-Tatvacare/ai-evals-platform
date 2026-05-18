import { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import { ToolStack } from './ToolStack';
import type { ToolCallPart } from '../types';

interface ToolGroupProps {
  tools: ToolCallPart[];
  autoCollapsed?: boolean;
}

function summarizeConsultation(tools: ToolCallPart[]): string {
  // One short generic line so the header doesn't wrap awkwardly.
  // The per-specialist breakdown is one click away (expand the group).
  const distinct = new Set(tools.map((t) => t.toolName)).size;
  if (distinct === 0) return '';
  if (distinct === 1) {
    return `Sherlock consulted 1 specialist`;
  }
  return `Sherlock consulted ${distinct} specialists`;
}

export function ToolGroup({ tools, autoCollapsed = false }: ToolGroupProps) {
  const [collapsed, setCollapsed] = useState(autoCollapsed);

  useEffect(() => {
    if (autoCollapsed) {
      setCollapsed(true);
    }
  }, [autoCollapsed]);

  if (tools.length === 0) {
    return null;
  }

  const heading = summarizeConsultation(tools);

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        aria-label={heading}
        className="inline-flex w-fit items-center gap-1.5 text-[11px] text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
      >
        <ChevronRight className={cn('h-3 w-3 transition-transform', !collapsed && 'rotate-90')} />
        <span className="font-mono uppercase tracking-[0.08em]">{heading}</span>
      </button>
      {!collapsed ? <ToolStack tools={tools} /> : null}
    </div>
  );
}
