import { useState } from 'react';
import { Plus, Search, Trash2 } from 'lucide-react';

import { Button, EmptyState, Input } from '@/components/ui';
import type { LLMProvider } from '@/services/api/aiSettingsApi';
import { useDiscoverModels } from '@/services/api/aiSettingsQueries';
import { notificationService } from '@/services/notifications/notificationService';
import { cn } from '@/utils';

interface ModelCurationProps {
  provider: LLMProvider;
  curatedModels: string[];
  onChange: (models: string[]) => void;
  /** Discovery is disabled until the provider row has a saved key. */
  disabled?: boolean;
}

export function ModelCuration({
  provider,
  curatedModels,
  onChange,
  disabled,
}: ModelCurationProps) {
  const isAzure = provider === 'azure_openai';
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<string[]>([]);
  const discover = useDiscoverModels();

  const handleAddDeployment = () => {
    const name = search.trim();
    if (!name) return;
    if (curatedModels.includes(name)) {
      notificationService.info(`Deployment "${name}" is already added.`);
      return;
    }
    onChange([...curatedModels, name]);
    setSearch('');
  };

  const handleSearch = async () => {
    if (isAzure) {
      handleAddDeployment();
      return;
    }
    try {
      const data = await discover.mutateAsync({ provider, search: search.trim() });
      setResults(data.models);
      if (data.models.length === 0) {
        notificationService.info('No models matched your search.');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Model discovery failed';
      notificationService.error(message);
    }
  };

  const handleAdd = (model: string) => {
    if (curatedModels.includes(model)) return;
    onChange([...curatedModels, model]);
  };

  const handleRemove = (model: string) => {
    onChange(curatedModels.filter((m) => m !== model));
  };

  const inputPlaceholder = isAzure
    ? 'Add deployment name (e.g. ai-evals-gpt-5.4-mini)'
    : 'Search models (e.g. gpt, claude, gemini)…';
  const ctaLabel = isAzure ? 'Add deployment' : 'Search';

  return (
    <section className="flex flex-col gap-3">
      <header className="flex items-center justify-between">
        <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">
          {isAzure ? 'Deployments' : 'Models'}
        </h3>
        <span className="text-[11px] text-[var(--text-secondary)]">
          {curatedModels.length} selected
        </span>
      </header>

      {isAzure && (
        <p className="text-[11px] text-[var(--text-secondary)]">
          Azure has no public model list — type each deployment name you
          created in the Azure portal (the same string you pass to the
          OpenAI SDK&rsquo;s <code>model</code> field).
        </p>
      )}

      <div className="flex items-stretch gap-2">
        <div className="flex-1">
          <Input
            placeholder={inputPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleSearch();
              }
            }}
            disabled={disabled}
            icon={<Search className="h-4 w-4" />}
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={handleSearch}
          disabled={disabled || (!isAzure && discover.isPending) || (isAzure && !search.trim())}
          isLoading={!isAzure && discover.isPending}
          icon={isAzure ? Plus : undefined}
        >
          {ctaLabel}
        </Button>
      </div>

      {!isAzure && results.length > 0 && (
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <header className="border-b border-dashed border-[var(--border-subtle)] px-3 py-2 text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
            Search results ({results.length})
          </header>
          <ul className="max-h-48 overflow-y-auto">
            {results.map((m) => {
              const isAdded = curatedModels.includes(m);
              return (
                <li
                  key={m}
                  className="flex items-center justify-between gap-2 px-3 py-1.5 hover:bg-[var(--bg-tertiary)]"
                >
                  <span className="truncate text-[13px] text-[var(--text-primary)]">
                    {m}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    icon={Plus}
                    onClick={() => handleAdd(m)}
                    disabled={isAdded}
                  >
                    {isAdded ? 'Added' : 'Add'}
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className={cn('flex flex-col gap-1')}>
        <header className="flex items-center justify-between">
          <h4 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
            Selected Models
          </h4>
        </header>
        {curatedModels.length === 0 ? (
          <EmptyState
            icon={Search}
            title="No models curated yet"
            description="Search for available models and add the ones you want to expose to users."
          />
        ) : (
          <ul className="flex flex-col gap-1">
            {curatedModels.map((m) => (
              <li
                key={m}
                className="flex items-center justify-between gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1.5"
              >
                <span className="truncate text-[13px] text-[var(--text-primary)]">
                  {m}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon={Trash2}
                  iconOnly
                  aria-label={`Remove ${m}`}
                  onClick={() => handleRemove(m)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
