import { useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/utils/cn';
import { Shimmer } from './Shimmer';
import { SHERLOCK_THINKING_PHRASES } from '../thinkingPhrases';

const ROTATE_INTERVAL_MS = 2200;
const SWAP_FADE_MS = 360;

function shufflePhrases(source: readonly string[]): string[] {
  const copy = [...source];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function longestOf(source: readonly string[]): string {
  return source.reduce((a, b) => (a.length > b.length ? a : b));
}

interface ThinkingIndicatorProps {
  phrases?: readonly string[];
  literalText?: string;
}

export function ThinkingIndicator({ phrases: phrasesProp, literalText }: ThinkingIndicatorProps = {}) {
  const source = phrasesProp && phrasesProp.length > 0 ? phrasesProp : SHERLOCK_THINKING_PHRASES;
  const shuffled = useMemo(() => shufflePhrases(source), [source]);
  const ghost = useMemo(() => longestOf(source), [source]);
  const [index, setIndex] = useState(0);
  const [swapping, setSwapping] = useState(false);
  const swapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const rotate = !literalText;

  useEffect(() => {
    if (!rotate) {
      return undefined;
    }
    const tick = window.setInterval(() => {
      setSwapping(true);
      swapTimerRef.current = setTimeout(() => {
        setIndex((i) => (i + 1) % shuffled.length);
        setSwapping(false);
      }, SWAP_FADE_MS);
    }, ROTATE_INTERVAL_MS);

    return () => {
      window.clearInterval(tick);
      if (swapTimerRef.current) {
        clearTimeout(swapTimerRef.current);
      }
    };
  }, [shuffled.length, rotate]);

  const currentText = literalText ?? shuffled[index];
  const ghostText = literalText ?? ghost;

  return (
    <div
      data-testid="sherlock-thinking"
      className="inline-flex items-center gap-2.5 font-mono text-[11px] leading-tight text-[var(--text-muted)]"
    >
      <Search className="h-3 w-3 shrink-0 animate-[chat-widget-sweep_2.4s_ease-in-out_infinite]" />
      <span className="relative inline-block">
        <span className="invisible whitespace-nowrap">{ghostText}</span>
        <span
          className={cn(
            'absolute inset-0 whitespace-nowrap transition-[opacity,transform] duration-[360ms] ease-out',
            rotate && swapping ? 'translate-y-[-3px] opacity-0' : 'translate-y-0 opacity-100',
          )}
        >
          <Shimmer>{currentText}</Shimmer>
        </span>
      </span>
    </div>
  );
}
