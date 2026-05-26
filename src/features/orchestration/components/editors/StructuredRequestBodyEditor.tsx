import { useEffect, useMemo, useState } from 'react';

import { Input } from '@/components/ui/Input';
import type { StructuredRequestBody } from '@/features/orchestration/types';

interface Props {
  value: StructuredRequestBody | undefined;
  onChange(next: StructuredRequestBody): void;
}

/** JSON body editor for `core.webhook_out`; leaves may be literals or `{"$payload": "field"}` refs. */
export function StructuredRequestBodyEditor({ value, onChange }: Props) {
  const initialText = useMemo(() => stringify(value), [value]);
  const [text, setText] = useState<string>(initialText);
  const [parseError, setParseError] = useState<string | null>(null);

  // Re-seed only when the incoming value isn't already what the current text
  // represents (external change / node switch). Re-seeding on our own onChange
  // round-trip would pretty-reformat mid-keystroke and jump the caret.
  useEffect(() => {
    if (!textRepresents(text, value)) {
      setText(stringify(value));
      setParseError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleChange = (next: string) => {
    setText(next);
    if (next.trim() === '') {
      setParseError(null);
      onChange({});
      return;
    }
    try {
      const parsed = JSON.parse(next) as StructuredRequestBody;
      setParseError(null);
      onChange(parsed);
    } catch (err) {
      setParseError(err instanceof Error ? err.message : 'Invalid JSON');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Tab') return;
    e.preventDefault();
    const el = e.currentTarget;
    const { selectionStart: start, selectionEnd: end } = el;
    handleChange(`${text.slice(0, start)}  ${text.slice(end)}`);
    requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = start + 2;
    });
  };

  return (
    <div className="flex flex-col gap-1">
      <textarea
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={12}
        spellCheck={false}
        className="block w-full resize-y rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-base)] px-2 py-1.5 font-mono text-xs leading-relaxed text-[var(--text-primary)] focus:border-[var(--color-brand)] focus:outline-none"
      />
      {parseError ? (
        <p className="text-xs text-[var(--color-error)]">JSON parse error: {parseError}</p>
      ) : null}
      <details className="text-xs text-[var(--text-secondary)]">
        <summary className="cursor-pointer">Insert reference helpers</summary>
        <RefHelper text={text} setText={handleChange} />
      </details>
    </div>
  );
}

// True when `text` parses to a value canonically equal to `value` — so the
// textarea already shows this value and re-seeding would only reformat it.
function textRepresents(text: string, value: StructuredRequestBody | undefined): boolean {
  if (text.trim() === '') {
    return value == null || (typeof value === 'object' && Object.keys(value).length === 0);
  }
  try {
    return JSON.stringify(JSON.parse(text)) === JSON.stringify(value ?? {});
  } catch {
    return false;
  }
}

function stringify(v: StructuredRequestBody | undefined): string {
  if (v === undefined) return '{}';
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return '{}';
  }
}

function RefHelper({
  text,
  setText,
}: {
  text: string;
  setText(next: string): void;
}) {
  const [field, setField] = useState('');
  const insert = () => {
    if (!field) return;
    const ref = `{ "$payload": "${field}" }`;
    setText(text.endsWith('\n') ? `${text}${ref}` : `${text}\n${ref}`);
    setField('');
  };
  return (
    <div className="mt-1 flex items-center gap-1">
      <Input
        value={field}
        onChange={(e) => setField(e.target.value)}
        placeholder="payload field name"
      />
      <button
        type="button"
        onClick={insert}
        className="rounded-[var(--radius-default)] border border-[var(--border-default)] px-2 py-0.5 hover:bg-[var(--bg-tertiary)]"
      >
        Insert reference
      </button>
    </div>
  );
}
