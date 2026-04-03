import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
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
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dropdownPosition, setDropdownPosition] = useState<{
    left: number;
    top: number;
    width: number;
    maxHeight: number;
  } | null>(null);

  const filtered = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.toLowerCase().trim();
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, search]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      const clickedTrigger = containerRef.current?.contains(target);
      const clickedDropdown = dropdownRef.current?.contains(target);
      if (!clickedTrigger && !clickedDropdown) {
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
  }, [disabled]);

  const updateDropdownPosition = useCallback(() => {
    const trigger = containerRef.current;
    if (!trigger) return;

    const rect = trigger.getBoundingClientRect();
    const viewportPadding = 8;
    const top = rect.bottom + 4;
    const width = Math.max(rect.width, 220);

    setDropdownPosition({
      left: Math.max(
        viewportPadding,
        Math.min(rect.left, window.innerWidth - width - viewportPadding),
      ),
      top,
      width,
      maxHeight: Math.max(160, window.innerHeight - top - viewportPadding),
    });
  }, []);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    updateDropdownPosition();
    requestAnimationFrame(() => inputRef.current?.focus());

    const handlePositionChange = () => updateDropdownPosition();
    window.addEventListener('resize', handlePositionChange);
    window.addEventListener('scroll', handlePositionChange, true);

    return () => {
      window.removeEventListener('resize', handlePositionChange);
      window.removeEventListener('scroll', handlePositionChange, true);
    };
  }, [isOpen, updateDropdownPosition]);

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
          values.length > 0 && 'border-[var(--border-brand)] bg-[var(--surface-brand-subtle)]',
          'disabled:opacity-50 disabled:cursor-not-allowed'
        )}
      >
        <span
          className={cn(
            'truncate',
            triggerLabel
              ? values.length > 0
                ? 'font-medium text-[var(--text-brand)]'
                : 'text-[var(--text-primary)]'
              : 'text-[var(--text-muted)]'
          )}
        >
          {triggerLabel ?? placeholder}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          {values.length > 0 && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                onChange([]);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  e.stopPropagation();
                  onChange([]);
                }
              }}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
            >
              <X className="h-3 w-3" />
            </span>
          )}
          <ChevronDown className="h-3.5 w-3.5 text-[var(--text-muted)]" />
        </div>
      </button>

      {isOpen && dropdownPosition && createPortal(
        <div
          ref={dropdownRef}
          className="fixed z-[9999] rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg"
          style={{
            left: dropdownPosition.left,
            top: dropdownPosition.top,
            width: dropdownPosition.width,
          }}
        >
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

          <div
            className="overflow-y-auto py-1"
            style={{ maxHeight: Math.min(dropdownPosition.maxHeight, 280) }}
          >
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
                      'transition-colors',
                      selected
                        ? 'bg-[var(--surface-brand-subtle)] text-[var(--text-brand)] hover:bg-[var(--surface-brand-hover)]'
                        : 'hover:bg-[var(--bg-hover)]'
                    )}
                  >
                    <span
                      className={cn(
                        'h-3.5 w-3.5 shrink-0 rounded border flex items-center justify-center',
                        selected
                          ? 'border-[var(--interactive-primary)] bg-[var(--interactive-primary)]'
                          : 'border-[var(--border-default)]'
                      )}
                    >
                      {selected && <Check className="h-2.5 w-2.5 text-[var(--text-on-color)]" />}
                    </span>
                    <span className="truncate">{opt.label}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
