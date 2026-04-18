import { BarChart3, FileText, Search, TrendingUp, Wrench } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { PromptTemplate } from '../types';

interface EmptyStateProps {
  appId: string;
  templates: PromptTemplate[];
  onSelect: (prompt: string) => void;
}

const TILE_ICONS = [BarChart3, TrendingUp, FileText, Wrench];

// Fallback tiles used to fill the 2×2 grid when the app config ships fewer
// than 4 templates. Keep prompts open-ended so they work across apps.
const FALLBACK_TILES: PromptTemplate[] = [
  { label: 'Explore available data', prompt: 'What data is available in this app?', category: 'Discover' },
  { label: 'Inspect a table', prompt: 'Inspect the schema of the main data table and list its columns', category: 'Schema' },
  { label: 'Browse saved blueprints', prompt: 'Show me the saved analytics blueprints for this app', category: 'Library' },
  { label: 'Summarise recent activity', prompt: 'Summarise the most recent runs and flag anything unusual', category: 'Overview' },
];

function kickerFor(template: PromptTemplate, index: number): string {
  if (template.category) {
    return template.category;
  }
  const label = template.label.toLowerCase();
  if (label.includes('compare') || label.includes('trend')) return 'Trend';
  if (label.includes('find') || label.includes('issue') || label.includes('violation')) return 'Audit';
  if (label.includes('summar') || label.includes('analyze')) return 'Analysis';
  if (label.includes('report') || label.includes('build')) return 'Craft';
  const fallbacks = ['Analysis', 'Trend', 'Audit', 'Craft'];
  return fallbacks[index % fallbacks.length];
}

export function EmptyState({ appId, templates, onSelect }: EmptyStateProps) {
  // Always show 4 — fill from fallback pool when the app doesn't provide enough.
  const seen = new Set<string>();
  const tiles: PromptTemplate[] = [];
  for (const t of [...templates, ...FALLBACK_TILES]) {
    if (tiles.length >= 4) break;
    if (seen.has(t.label.toLowerCase())) continue;
    seen.add(t.label.toLowerCase());
    tiles.push(t);
  }

  return (
    <div className="flex min-h-full flex-col gap-5 px-4 py-6">
      {/* Eyebrow — grounds the conversation in the current app */}
      <div className="flex items-center gap-2.5 text-[10px] font-medium uppercase tracking-[0.2em] text-[var(--text-muted)]">
        <span className="h-px w-6 bg-[var(--text-muted)]" />
        <span>Case open · {appId}</span>
      </div>

      {/* Hero — glyph + headline + sub */}
      <div className="flex items-start gap-3.5">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-brand-subtle)] text-[var(--text-brand)]">
          <Search className="h-[22px] w-[22px]" strokeWidth={1.6} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[19px] font-normal leading-[1.2] tracking-[-0.01em] text-[var(--text-primary)]">
            Where shall we <em className="font-normal italic text-[var(--text-brand)]">begin?</em>
          </h3>
          <p className="mt-1 text-xs leading-[1.55] text-[var(--text-muted)]">
            Pull schema, run queries, chart trends, or compose a blueprint — all from one conversation.
          </p>
        </div>
      </div>

      {/* Starting prompts */}
      {tiles.length > 0 ? (
        <div>
          <div className="mb-2.5 text-[9px] font-medium uppercase tracking-[0.22em] text-[var(--text-muted)]">
            Start with these...
          </div>
          <div className="grid grid-cols-2 gap-2">
            {tiles.map((template, i) => {
              const Icon = TILE_ICONS[i % TILE_ICONS.length];
              return (
                <button
                  key={`${template.label}-${i}`}
                  type="button"
                  onClick={() => onSelect(template.prompt)}
                  className={cn(
                    'group flex flex-col gap-2.5 rounded-xl p-3 text-left transition-colors',
                    'border border-[var(--border-tile)] bg-[var(--bg-tile)]',
                    'hover:border-[var(--border-tile-hover)] hover:bg-[var(--bg-tile-hover)]',
                    'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--interactive-primary)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--bg-primary)]',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Icon className="h-3.5 w-3.5 text-[var(--text-muted)] transition-colors group-hover:text-[var(--text-brand)]" strokeWidth={1.8} />
                    <span className="text-[9px] font-medium uppercase tracking-[0.2em] text-[var(--text-muted)]">
                      {kickerFor(template, i)}
                    </span>
                  </div>
                  <div className="text-[13px] font-normal italic leading-[1.25] text-[var(--text-primary)]">
                    {template.label}.
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

    </div>
  );
}
