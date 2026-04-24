/**
 * RecordWorkspace — two-column detail layout for CRM-style records.
 *
 * Left: sticky summary rail with identity, key metrics, meta. Stays in view
 *       while the right column scrolls.
 * Right: tabbed detail panel (Overview / Timeline / Evaluations / …).
 *
 * Designed to live inside a `PageSurface`, which provides the title, back
 * button, and action slot. Kept deliberately generic — no CRM or app
 * vocabulary — so any detail page (Lead, Contact, Deal, Case) can compose it.
 *
 * Transitions match the house motion grammar: spring `stiffness 400, damping
 * 38, mass 0.9` (same config as Tabs underline) and honour
 * `useReducedMotion()`.
 */

import { useState, type ReactNode } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion';
import { cn } from '@/utils';

// House spring for record-workspace transitions. Matches Tabs.tsx to keep the
// whole page on one animation feel.
const WORKSPACE_SPRING = { type: 'spring' as const, stiffness: 400, damping: 38, mass: 0.9 };

export interface RecordWorkspaceTab {
  id: string;
  label: string;
  /** Optional badge node (count, status dot). */
  badge?: ReactNode;
  content: ReactNode;
  /** Hide the tab from the strip entirely (useful when it depends on data). */
  hidden?: boolean;
}

interface RecordWorkspaceProps {
  /** Sticky left rail — compose from `SectionBlock`, `MetricChip`, badges, etc. */
  summary: ReactNode;
  tabs: RecordWorkspaceTab[];
  defaultTab?: string;
  /** Called whenever the user switches tabs. Receives tab id. */
  onTabChange?: (id: string) => void;
  /** Width of the summary rail. Defaults to 320px. */
  railWidth?: number;
  className?: string;
}

export function RecordWorkspace({
  summary,
  tabs,
  defaultTab,
  onTabChange,
  railWidth = 320,
  className,
}: RecordWorkspaceProps) {
  const visibleTabs = tabs.filter((t) => !t.hidden);
  const initial = defaultTab && visibleTabs.some((t) => t.id === defaultTab)
    ? defaultTab
    : visibleTabs[0]?.id ?? '';
  const [activeId, setActiveId] = useState(initial);
  const prefersReducedMotion = useReducedMotion();
  const activeTab = visibleTabs.find((t) => t.id === activeId) ?? visibleTabs[0];

  const handleSelect = (id: string) => {
    if (id === activeId) return;
    setActiveId(id);
    onTabChange?.(id);
  };

  return (
    <div className={cn('flex min-h-0 flex-1 gap-6', className)}>
      {/* Left rail — sticky within the scrolling right column, separated by a
          hairline. Intentionally flat: no gradient, no fill; the rail is
          structural, not decorative. */}
      <aside
        className="flex flex-shrink-0 flex-col border-r border-[var(--border-subtle)] pr-6"
        style={{ width: railWidth }}
      >
        <div className="sticky top-0 flex flex-col gap-6">
          {summary}
        </div>
      </aside>

      {/* Right panel */}
      <div className="flex min-w-0 min-h-0 flex-1 flex-col">
        {/* Tab strip — spring-underline, mirrors `Tabs.tsx` aesthetic. */}
        <div
          role="tablist"
          aria-label="Record sections"
          className="relative flex flex-shrink-0 items-end gap-6 border-b border-[var(--border-subtle)]"
        >
          {visibleTabs.map((tab) => {
            const isActive = tab.id === activeId;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                type="button"
                onClick={() => handleSelect(tab.id)}
                className={cn(
                  'relative flex items-center gap-2 pb-2.5 pt-1 text-[13px] font-medium transition-colors outline-none',
                  isActive
                    ? 'text-[var(--text-primary)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]',
                )}
              >
                <span>{tab.label}</span>
                {tab.badge && (
                  <span className="text-[11px] text-[var(--text-muted)]">{tab.badge}</span>
                )}
                {isActive && (
                  <motion.span
                    layoutId="record-workspace-underline"
                    className="absolute left-0 right-0 -bottom-px h-[2px] bg-[var(--interactive-primary)]"
                    transition={prefersReducedMotion ? { duration: 0 } : WORKSPACE_SPRING}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Panel body — spring-eased cross-fade between tabs.
            `pr-2` reserves gutter for the overlay scrollbar so any child
            element at the right edge (icon rings, badges, tab underlines)
            is never clipped by the scrollbar.
            `pb-4` keeps a little breathing room under the last section. */}
        <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto pt-5 pr-2 pb-4 pl-1">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={activeTab?.id}
              initial={prefersReducedMotion ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
              transition={prefersReducedMotion ? { duration: 0 } : WORKSPACE_SPRING}
              className="flex min-h-0 flex-1 flex-col gap-6"
            >
              {activeTab?.content}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
