import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { ChevronDown, Search, X, Check } from 'lucide-react';
import { cn } from '@/utils';

export interface MultiSelectOption {
  value: string;
  label: string;
}

interface MultiSelectProps {
  values: string[];
  onChange: (values: string[]) => void;
  options: MultiSelectOption[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function MultiSelect({
  values,
  onChange,
  options,
  placeholder = 'Select...',
  className,
  disabled = false,
}: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.toLowerCase().trim();
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, search]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSearch('');
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const openDropdown = useCallback(() => {
    if (disabled) return;
    setIsOpen(true);
    setSearch('');
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [disabled]);

  const toggleOption = useCallback(
    (value: string) => {
      if (values.includes(value)) {
        onChange(values.filter((v) => v !== value));
      } else {
        onChange([...values, value]);
      }
    },
    [values, onChange]
  );

  const triggerLabel = useMemo(() => {
    if (values.length === 0) return null;
    const labels = values
      .map((value) => options.find((option) => option.value === value)?.label || value)
      .filter(Boolean);
    if (labels.length === 1) return labels[0];
    if (labels.length === 2) return labels.join(', ');
    return `${labels.length} selected`;
  }, [options, values]);

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => (isOpen ? setIsOpen(false) : openDropdown())}
        disabled={disabled}
        className={cn(
          'w-full px-2.5 py-1.5 rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)]',
          'text-xs text-left flex items-center justify-between gap-2',
          'focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]',
          'disabled:opacity-50 disabled:cursor-not-allowed'
        )}
      >
        <span className={cn('truncate', triggerLabel ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]')}>
          {triggerLabel ?? placeholder}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          {values.length > 0 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange([]);
              }}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X className="h-3 w-3" />
            </button>
          )}
          <ChevronDown className="h-3.5 w-3.5 text-[var(--text-muted)]" />
        </div>
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 w-full min-w-[220px] rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--border-default)]">
            <Search className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="flex-1 bg-transparent text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          <div className="max-h-[220px] overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-[var(--text-muted)]">No matches found</div>
            ) : (
              filtered.map((opt) => {
                const selected = values.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => toggleOption(opt.value)}
                    className={cn(
                      'w-full px-3 py-1.5 text-left text-xs flex items-center gap-2',
                      'hover:bg-[var(--bg-hover)] transition-colors',
                      selected && 'text-[var(--text-brand)]'
                    )}
                  >
                    <span
                      className={cn(
                        'h-3.5 w-3.5 shrink-0 rounded border flex items-center justify-center',
                        selected
                          ? 'bg-[var(--color-brand-accent)] border-[var(--color-brand-accent)]'
                          : 'border-[var(--border-default)]'
                      )}
                    >
                      {selected && <Check className="h-2.5 w-2.5 text-white" />}
                    </span>
                    <span className="truncate">{opt.label}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
