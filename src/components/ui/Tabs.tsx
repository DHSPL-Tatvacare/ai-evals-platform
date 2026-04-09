import { type ReactNode, useEffect, useState } from 'react';
import { cn } from '@/utils';

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

  const firstTabId = tabs[0]?.id;

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
    <div className={cn(fillHeight && 'flex flex-col h-full min-h-0', className)}>
      <div className="flex border-b border-[var(--border-subtle)] shrink-0 bg-[var(--bg-primary)]">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={cn(
              'px-4 py-2 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]',
              activeTab === tab.id
                ? 'border-b-2 border-[var(--border-brand)] text-[var(--text-brand)]'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className={cn(fillHeight ? 'pt-2 flex-1 min-h-0 overflow-hidden' : 'pt-4')}>
        {tabs.map((tab) => {
          if (mountStrategy === 'active-only' && activeTab !== tab.id) {
            return null;
          }
          return (
            <div
              key={tab.id}
              className={cn(
                mountStrategy === 'all' && activeTab !== tab.id && 'hidden',
                fillHeight && activeTab === tab.id && 'h-full overflow-y-auto'
              )}
            >
              {tab.content}
            </div>
          );
        })}
      </div>
    </div>
  );
}
