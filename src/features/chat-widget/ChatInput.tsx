import { useState, useCallback, useRef, useEffect } from 'react';
import { ArrowUp, Square } from 'lucide-react';

import { cn } from '@/utils/cn';
import { FlowingBorder } from '@/components/ui/FlowingBorder';
import { usePageContext } from '@/features/orchestration/copilot/usePageContext';
import { useChatWidgetStore } from './useChatWidget';
import { BuilderContextChip } from './components/BuilderContextChip';
import { ContextRing } from './components/ContextRing';

interface ChatInputProps {
  onSend: (text: string) => void;
  onStop?: () => void;
  disabled: boolean;
  showStop?: boolean;
  placeholder?: string;
}

const COMPOSER_MAX_HEIGHT_PX = 120;
const COMPOSER_MAX_CHARS = 12000;

export function ChatInput({ onSend, onStop, disabled, showStop = false, placeholder }: ChatInputProps) {
  const [value, setValue] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  const pageContext = usePageContext();
  const working = useChatWidgetStore((s) => s.status) === 'sending';
  const showChip = pageContext.kind === 'orchestration_builder';

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text || disabled) return;
    setValue('');
    onSend(text);
    if (ref.current) ref.current.style.height = 'auto';
  }, [value, disabled, onSend]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`;
  }, [value]);

  const canSend = !!value.trim() && !disabled;

  return (
    <div className="p-2 border-t border-[var(--border-default)]">
      <FlowingBorder
        active={working}
        className={cn(
          'rounded-lg border bg-[var(--bg-secondary)] transition-colors',
          // While a turn is active the flowing border owns the edge; otherwise a
          // resting/focus border. Never dim the wrapper here — that washes out
          // the active animation.
          working
            ? 'border-transparent'
            : cn(
                'border-[var(--border-default)]',
                'focus-within:border-[var(--color-brand-accent)]',
                'focus-within:ring-1 focus-within:ring-[var(--color-brand-accent)]',
              ),
        )}
      >
        {showChip ? (
          <div className="px-1.5 pt-1.5 pb-0.5">
            <BuilderContextChip pageContext={pageContext} working={working} />
          </div>
        ) : null}

        <div className="flex items-end gap-1.5 px-2 py-1.5">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={placeholder ?? 'Type a message...'}
            disabled={disabled}
            rows={1}
            maxLength={COMPOSER_MAX_CHARS}
            className={cn(
              'block flex-1 min-w-0 resize-none bg-transparent border-0 outline-none overflow-y-auto',
              'py-0.5 text-[13px] leading-snug',
              'text-[var(--text-primary)] placeholder:text-[var(--text-muted)]',
            )}
            style={{ maxHeight: `${COMPOSER_MAX_HEIGHT_PX}px` }}
          />
          <ContextRing />
          {showStop ? (
            <button
              type="button"
              onClick={onStop}
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                'border border-[var(--border-error)] bg-[var(--surface-error)]',
                'text-[var(--color-error)] transition-colors',
                'hover:bg-[color-mix(in_srgb,var(--surface-error)_70%,var(--bg-primary))]',
                'focus-visible:outline-none focus-visible:ring-2',
                'focus-visible:ring-[var(--color-brand-accent)]',
              )}
              title="Stop"
              aria-label="Stop"
            >
              <Square className="h-2.5 w-2.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                'transition-colors',
                canSend
                  ? 'bg-[var(--color-brand-primary)] text-[var(--text-inverse)] hover:bg-[var(--color-brand-primary-hover)]'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] cursor-not-allowed',
                'focus-visible:outline-none focus-visible:ring-2',
                'focus-visible:ring-[var(--color-brand-accent)]',
              )}
              aria-label="Send"
              title="Send"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </FlowingBorder>
    </div>
  );
}
