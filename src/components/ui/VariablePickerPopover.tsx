import { useState, useRef, useEffect, useMemo } from 'react';
import { Code, Search } from 'lucide-react';
import { Button, Popover, PopoverTrigger, PopoverContent, Tooltip } from '@/components/ui';
import { useAppConfig } from '@/hooks';
import { evaluatorsRepository } from '@/services/api/evaluatorsApi';
import { useAppStore } from '@/stores';
import { cn } from '@/utils';
import type { AppId, Listing, PromptType, VariableInfo } from '@/types';

interface VariablePickerPopoverProps {
  listing?: Listing;
  appId?: AppId;
  staticVariables?: VariableInfo[];
  onInsert: (variable: string) => void;
  promptType?: PromptType;
  buttonLabel?: string;
  className?: string;
}

export function VariablePickerPopover({
  listing,
  appId,
  staticVariables = [],
  onInsert,
  buttonLabel = 'Variables',
  className,
}: VariablePickerPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [variables, setVariables] = useState<VariableInfo[]>([]);
  const [apiPaths, setApiPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const currentAppId = useAppStore((state) => state.currentApp);

  const effectiveAppId = appId || listing?.appId || currentAppId;
  const appConfig = useAppConfig(effectiveAppId);
  const sourceType = listing?.sourceType;
  const listingId = listing?.id;

  // Fetch variables from backend when popover opens
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const [vars, paths] = await Promise.all([
          appConfig.evaluator.dynamicVariableSources.registry
            ? evaluatorsRepository.getVariables(effectiveAppId, sourceType)
            : Promise.resolve([]),
          listingId && sourceType === 'api' && appConfig.evaluator.dynamicVariableSources.listingApiPaths
            ? evaluatorsRepository.getApiPaths(listingId)
            : Promise.resolve([]),
        ]);
        if (!cancelled) {
          const mergedVariables = [...staticVariables, ...vars].reduce<VariableInfo[]>((items, variable) => {
            if (items.some((existing) => existing.key === variable.key)) {
              return items;
            }
            items.push(variable);
            return items;
          }, []);
          setVariables(mergedVariables);
          setApiPaths(paths);
        }
      } catch {
        if (!cancelled) {
          setVariables(staticVariables);
          setApiPaths([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [
    appConfig.evaluator.dynamicVariableSources.listingApiPaths,
    appConfig.evaluator.dynamicVariableSources.registry,
    effectiveAppId,
    isOpen,
    listingId,
    sourceType,
    staticVariables,
  ]);

  // Group variables by category for display
  const groupedVariables = useMemo(() => {
    const groups = new Map<string, VariableInfo[]>();
    for (const v of variables) {
      const cat = v.category || 'General';
      if (!groups.has(cat)) groups.set(cat, []);
      groups.get(cat)!.push(v);
    }
    return groups;
  }, [variables]);

  // Filter by search
  const filteredGroups = useMemo(() => {
    if (!search) return groupedVariables;
    const q = search.toLowerCase();
    const filtered = new Map<string, VariableInfo[]>();
    for (const [cat, vars] of groupedVariables) {
      const matching = vars.filter(
        (v) =>
          v.key.toLowerCase().includes(q) ||
          v.displayName.toLowerCase().includes(q) ||
          v.description.toLowerCase().includes(q),
      );
      if (matching.length > 0) filtered.set(cat, matching);
    }
    return filtered;
  }, [groupedVariables, search]);

  const filteredApi = useMemo(
    () =>
      apiPaths.filter((path) => !search || path.toLowerCase().includes(search.toLowerCase())),
    [apiPaths, search],
  );

  const handleInsert = (variable: string) => {
    onInsert(variable);
    setIsOpen(false);
    setSearch('');
  };

  return (
    <Popover
      open={isOpen}
      onOpenChange={(open) => {
        setIsOpen(open);
        if (!open) setSearch('');
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="secondary" size="sm" className={cn('h-8 text-xs', className)}>
          <Code className="h-3.5 w-3.5 mr-1.5" />
          {buttonLabel}
        </Button>
      </PopoverTrigger>

      <PopoverContent
        className="w-[420px] p-0 bg-[var(--bg-primary)] border-[var(--border-default)] shadow-xl"
        align="start"
      >
        {/* Search */}
        <div className="p-3 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--text-muted)]" />
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search variables..."
              className={cn(
                'w-full h-8 pl-9 pr-3 text-xs rounded-md',
                'bg-[var(--bg-surface)] text-[var(--text-primary)]',
                'border border-[var(--border-default)]',
                'placeholder:text-[var(--text-muted)]',
                'focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/20',
              )}
              autoFocus
            />
          </div>
        </div>

        <div className="max-h-96 overflow-y-auto">
          {loading ? (
            <p className="text-xs text-[var(--text-muted)] p-4 text-center">Loading variables…</p>
          ) : (
            <>
              {/* Registry Variables grouped by category */}
              {filteredGroups.size === 0 && filteredApi.length === 0 ? (
                <p className="text-xs text-[var(--text-muted)] p-4 text-center">
                  No variables found
                </p>
              ) : (
                <>
                  {[...filteredGroups.entries()].map(([category, vars]) => (
                    <div key={category} className="p-3">
                      <h4 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wide">
                        {category}
                      </h4>
                      <div className="space-y-1">
                        {vars.map((v) => {
                          const tooltipContent = v.example
                            ? `${v.description}\nExample: ${v.example}`
                            : v.description;
                          return (
                            <Tooltip key={v.key} content={tooltipContent} position="right">
                              <button
                                onClick={() => handleInsert(`{{${v.key}}}`)}
                                className={cn(
                                  'w-full text-left px-2 py-1.5 rounded text-xs transition-colors',
                                  'hover:bg-[var(--interactive-secondary)] cursor-pointer',
                                )}
                              >
                                <div className="font-mono font-medium text-[var(--color-brand-accent)]">
                                  {`{{${v.key}}}`}
                                </div>
                                <div className="text-[var(--text-muted)] text-[11px] mt-0.5">
                                  {v.description}
                                </div>
                              </button>
                            </Tooltip>
                          );
                        })}
                      </div>
                    </div>
                  ))}

                  {/* API Variables */}
                  {filteredApi.length > 0 && (
                    <div className="p-3 pt-2 border-t border-[var(--border-subtle)]">
                      <h4 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wide">
                        API Response Data
                      </h4>
                      <div className="space-y-0.5">
                        {filteredApi.slice(0, 50).map((path) => (
                          <button
                            key={path}
                            onClick={() => handleInsert(`{{${path}}}`)}
                            className={cn(
                              'w-full text-left px-2 py-1 rounded text-xs transition-colors font-mono',
                              'hover:bg-[var(--interactive-secondary)]',
                              'text-[var(--text-primary)]',
                            )}
                          >
                            {`{{${path}}}`}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
