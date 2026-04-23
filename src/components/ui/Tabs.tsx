import { type ReactNode, useCallback, useEffect, useId, useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { cn } from '@/utils';
import { TabsHeaderActionsContext } from './TabsHeaderActionsContext';

const TAB_UNDERLINE_SPRING = { type: 'spring' as const, stiffness: 400, damping: 38, mass: 0.9 };

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
  onChange?: (tabId: string) => void;
  beforeChange?: (tabId: string, commit: () => void) => void;
  className?: string;
  /** When true, tabs fill available height and content scrolls internally */
  fillHeight?: boolean;
  /** Controls whether inactive tabs stay mounted or unmount until active */
  mountStrategy?: 'all' | 'active-only';
}

export function Tabs({
  tabs,
  defaultTab,
  onChange,
  beforeChange,
  className,
  fillHeight,
  mountStrategy = 'all',
}: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0]?.id);
  const [headerActionsByTab, setHeaderActionsByTab] = useState<Record<string, ReactNode | null>>({});
  const instanceId = useId();
  const underlineLayoutId = `tabs-underline-${instanceId}`;
  const prefersReducedMotion = useReducedMotion();

  const firstTabId = tabs[0]?.id;
  const activeHeaderActions = activeTab ? headerActionsByTab[activeTab] ?? null : null;

  const setHeaderActions = useCallback((tabId: string, actions: ReactNode | null) => {
    setHeaderActionsByTab((prev) => {
      if ((prev[tabId] ?? null) === actions) {
        return prev;
      }
      return {
        ...prev,
        [tabId]: actions,
      };
    });
  }, []);

  const contextValue = useMemo(
    () => ({ setHeaderActions }),
    [setHeaderActions],
  );

  useEffect(() => {
    const target = defaultTab || firstTabId;
    if (target && target !== activeTab) {
      setActiveTab(target);
    }
    // Only re-run when defaultTab explicitly changes, not on every tabs array re-creation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultTab]);

  const handleTabChange = (tabId: string) => {
    const commit = () => {
      setActiveTab(tabId);
      onChange?.(tabId);
    };

    if (beforeChange) {
      beforeChange(tabId, commit);
      return;
    }

    commit();
  };

  return (
    <TabsHeaderActionsContext.Provider value={contextValue}>
      <div className={cn(fillHeight && 'flex flex-col h-full min-h-0', className)}>
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="flex min-w-0 shrink border-b border-transparent">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={cn(
                    'relative px-4 py-2 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]',
                    isActive
                      ? 'text-[var(--text-brand)]'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  )}
                >
                  {tab.label}
                  {isActive ? (
                    <motion.span
                      layoutId={underlineLayoutId}
                      className="absolute left-0 right-0 bottom-[-1px] h-0.5 bg-[var(--border-brand)]"
                      transition={prefersReducedMotion ? { duration: 0 } : TAB_UNDERLINE_SPRING}
                    />
                  ) : null}
                </button>
              );
            })}
          </div>
          {activeHeaderActions ? (
            <div className="flex shrink-0 items-center gap-2 px-1">
              {activeHeaderActions}
            </div>
          ) : null}
        </div>
        <div className={cn(fillHeight ? 'pt-2 flex-1 min-h-0 flex flex-col' : 'pt-4')}>
          {tabs.map((tab) => {
            if (mountStrategy === 'active-only' && activeTab !== tab.id) {
              return null;
            }
            return (
              <div
                key={tab.id}
                className={cn(
                  mountStrategy === 'all' && activeTab !== tab.id && 'hidden',
                  fillHeight && activeTab === tab.id && 'flex-1 min-h-0 overflow-y-auto'
                )}
              >
                {tab.content}
              </div>
            );
          })}
        </div>
      </div>
    </TabsHeaderActionsContext.Provider>
  );
}
