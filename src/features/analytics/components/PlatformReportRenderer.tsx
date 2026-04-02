import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { BarChart3, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import type { AppId, LLMProvider } from '@/types';
import type {
  PlatformCrossRunNarrative,
  PlatformCrossRunPayload,
  PlatformReportSection,
  PlatformRunNarrative,
  PlatformRunReportPayload,
} from '@/types/platformReports';
import { Button, EmptyState, LLMConfigSection } from '@/components/ui';
import { reportsApi } from '@/services/api/reportsApi';
import { useCrossRunStore, hasProviderCredentials, LLM_PROVIDERS, useLLMSettingsStore } from '@/stores';
import { notificationService } from '@/services/notifications';
import { useAppConfig } from '@/hooks';
import SectionHeader from '@/features/evalRuns/components/report/shared/SectionHeader';
import CalloutBox from '@/features/evalRuns/components/report/shared/CalloutBox';
import { cn } from '@/utils/cn';

function toneClass(tone: string): string {
  if (tone === 'positive' || tone === 'success') return 'text-[var(--color-success)]';
  if (tone === 'warning') return 'text-[var(--color-warning)]';
  if (tone === 'negative' || tone === 'danger' || tone === 'error') return 'text-[var(--color-error)]';
  return 'text-[var(--text-secondary)]';
}

function calloutVariant(tone: string): 'info' | 'success' | 'warning' | 'danger' {
  if (tone === 'positive' || tone === 'success') return 'success';
  if (tone === 'warning') return 'warning';
  if (tone === 'negative' || tone === 'danger' || tone === 'error') return 'danger';
  return 'info';
}

function HeatCell({ tone, value }: { tone: string; value: number | null }) {
  const bg =
    tone === 'positive' || tone === 'success'
      ? 'bg-emerald-500/15'
      : tone === 'warning'
        ? 'bg-amber-500/15'
        : tone === 'negative' || tone === 'danger' || tone === 'error'
          ? 'bg-rose-500/15'
          : 'bg-[var(--bg-tertiary)]';
  return (
    <td className={cn('px-3 py-2 text-center text-xs border border-[var(--border-subtle)]', bg)}>
      {value == null ? '—' : value}
    </td>
  );
}

function SectionContent({ section }: { section: PlatformReportSection }) {
  if (section.type === 'summary_cards') {
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {section.data.map((item) => (
          <div key={item.key} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{item.label}</div>
            <div className={cn('mt-2 text-2xl font-bold', toneClass(item.tone))}>{item.value}</div>
            {item.subtitle && <div className="mt-1 text-xs text-[var(--text-muted)]">{item.subtitle}</div>}
          </div>
        ))}
      </div>
    );
  }

  if (section.type === 'narrative') {
    const narrative = section.data as PlatformRunNarrative | PlatformCrossRunNarrative;
    return (
      <div className="space-y-4">
        <CalloutBox variant="insight" title="Executive Summary">
          {narrative.executiveSummary}
        </CalloutBox>
        {'trendAnalysis' in narrative && narrative.trendAnalysis && (
          <CalloutBox variant="info" title="Trend Analysis">
            {narrative.trendAnalysis}
          </CalloutBox>
        )}
        {'issues' in narrative && narrative.issues.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2">
            {narrative.issues.map((issue) => (
              <div key={`${issue.area}-${issue.title}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
                <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{issue.area}</div>
                <div className="mt-1 font-semibold text-[var(--text-primary)]">{issue.title}</div>
                <div className="mt-2 text-sm text-[var(--text-secondary)]">{issue.summary}</div>
              </div>
            ))}
          </div>
        )}
        {'recommendations' in narrative && narrative.recommendations.length > 0 && (
          <div className="space-y-3">
            {narrative.recommendations.map((item, index) => {
              const rationale = 'rationale' in item && typeof item.rationale === 'string' ? item.rationale : null;
              const expectedImpact = 'expectedImpact' in item && typeof item.expectedImpact === 'string' ? item.expectedImpact : null;
              return (
                <div key={`${item.priority}-${index}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
                  <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{item.priority}</div>
                  <div className="mt-1 text-sm text-[var(--text-primary)]">{item.action}</div>
                  {rationale && <div className="mt-1 text-sm text-[var(--text-secondary)]">{rationale}</div>}
                  {expectedImpact && <div className="mt-1 text-sm text-[var(--text-secondary)]">{expectedImpact}</div>}
                </div>
              );
            })}
          </div>
        )}
        {'criticalPatterns' in narrative && narrative.criticalPatterns.length > 0 && (
          <div className="space-y-3">
            {narrative.criticalPatterns.map((item, index) => (
              <div key={`${item.title}-${index}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
                <div className="font-semibold text-[var(--text-primary)]">{item.title}</div>
                <div className="mt-1 text-sm text-[var(--text-secondary)]">{item.summary}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (section.type === 'metric_breakdown') {
    return (
      <div className="space-y-3">
        {section.data.map((item) => {
          const percent = item.maxValue > 0 ? Math.min(Math.max((item.value / item.maxValue) * 100, 0), 100) : 0;
          return (
            <div key={item.key}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="text-[var(--text-secondary)]">{item.label}</span>
                <span className={toneClass(item.tone)}>{item.value.toFixed(1)}{item.unit ?? ''}</span>
              </div>
              <div className="h-2 rounded-full bg-[var(--bg-tertiary)]">
                <div
                  className={cn(
                    'h-2 rounded-full',
                    item.tone === 'positive' || item.tone === 'success'
                      ? 'bg-emerald-500'
                      : item.tone === 'warning'
                        ? 'bg-amber-500'
                        : item.tone === 'negative' || item.tone === 'danger' || item.tone === 'error'
                          ? 'bg-rose-500'
                          : 'bg-[var(--color-info)]',
                  )}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (section.type === 'distribution_chart') {
    return (
      <div className="space-y-4">
        {section.data.map((series) => (
          <div key={`${series.label}-${series.categories.join('-')}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 font-semibold text-[var(--text-primary)]">{series.label}</div>
            <div className="space-y-2">
              {series.categories.map((category, index) => (
                <div key={`${series.label}-${category}`} className="flex items-center justify-between text-sm">
                  <span className="text-[var(--text-secondary)]">{category}</span>
                  <span className="font-medium text-[var(--text-primary)]">{series.values[index] ?? 0}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (section.type === 'compliance_table') {
    return (
      <div className="overflow-x-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)]">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)]">
              <th className="px-4 py-3 text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">Rule</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Passed</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Failed</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Rate</th>
            </tr>
          </thead>
          <tbody>
            {section.data.map((row) => (
              <tr key={row.key} className="border-b border-[var(--border-subtle)] last:border-b-0">
                <td className="px-4 py-3 text-[var(--text-primary)]">{row.label}</td>
                <td className="px-4 py-3 text-right text-[var(--text-secondary)]">{row.passed}</td>
                <td className="px-4 py-3 text-right text-[var(--text-secondary)]">{row.failed}</td>
                <td className={cn('px-4 py-3 text-right font-medium', toneClass(row.rate >= 85 ? 'positive' : row.rate >= 60 ? 'warning' : 'negative'))}>
                  {row.rate.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (section.type === 'heatmap') {
    return (
      <div className="overflow-x-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)]">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">Metric</th>
              {section.data.columns.map((column) => (
                <th key={column} className="px-3 py-2 text-center text-xs uppercase tracking-wide text-[var(--text-muted)]">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {section.data.rows.map((row) => (
              <tr key={row.key}>
                <td className="px-3 py-2 text-sm text-[var(--text-primary)] border border-[var(--border-subtle)]">{row.label}</td>
                {row.cells.map((cell, index) => (
                  <HeatCell key={`${row.key}-${index}`} tone={cell.tone} value={cell.value} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (section.type === 'entity_slices') {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {section.data.map((item) => (
          <div key={item.entityId} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="font-semibold text-[var(--text-primary)]">{item.label}</div>
            <dl className="mt-3 space-y-1">
              {Object.entries(item.summary).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between gap-4 text-sm">
                  <dt className="text-[var(--text-muted)]">{key}</dt>
                  <dd className="text-[var(--text-primary)]">{String(value)}</dd>
                </div>
              ))}
              {item.details && Object.entries(item.details).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between gap-4 text-sm">
                  <dt className="text-[var(--text-muted)]">{key}</dt>
                  <dd className="text-[var(--text-secondary)]">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    );
  }

  if (section.type === 'flags') {
    return (
      <div className="overflow-x-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)]">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)]">
              <th className="px-4 py-3 text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">Flag</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Relevant</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Present</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Attempted</th>
              <th className="px-4 py-3 text-right text-xs uppercase tracking-wide text-[var(--text-muted)]">Accepted</th>
            </tr>
          </thead>
          <tbody>
            {section.data.map((item) => (
              <tr key={item.key} className="border-b border-[var(--border-subtle)] last:border-b-0">
                <td className="px-4 py-3 text-[var(--text-primary)]">{item.label}</td>
                <td className="px-4 py-3 text-right text-[var(--text-secondary)]">{item.relevant}</td>
                <td className="px-4 py-3 text-right text-[var(--text-secondary)]">{item.present}</td>
                <td className="px-4 py-3 text-right text-[var(--text-secondary)]">{item.attempted ?? '—'}</td>
                <td className="px-4 py-3 text-right text-[var(--text-secondary)]">{item.accepted ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (section.type === 'issues_recommendations') {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          {section.data.issues.map((issue, index) => (
            <div key={`${issue.area}-${index}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
              <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{issue.priority}</div>
              <div className="mt-1 font-semibold text-[var(--text-primary)]">{issue.title}</div>
              <div className="mt-1 text-sm text-[var(--text-secondary)]">{issue.summary}</div>
            </div>
          ))}
        </div>
        <div className="space-y-3">
          {section.data.recommendations.map((item, index) => (
            <div key={`${item.title}-${index}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
              <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{item.priority}</div>
              <div className="mt-1 font-semibold text-[var(--text-primary)]">{item.title}</div>
              <div className="mt-1 text-sm text-[var(--text-secondary)]">{item.action}</div>
              {item.expectedImpact && <div className="mt-1 text-sm text-[var(--text-muted)]">{item.expectedImpact}</div>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (section.type === 'exemplars') {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {section.data.map((item) => (
          <div key={item.itemId} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="font-semibold text-[var(--text-primary)]">{item.label}</div>
              {item.score != null && <div className="text-sm text-[var(--text-secondary)]">{item.score.toFixed(1)}</div>}
            </div>
            <div className="mt-2 text-sm text-[var(--text-secondary)]">{item.summary}</div>
            {item.details && (
              <dl className="mt-3 space-y-1 text-sm">
                {Object.entries(item.details).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-4">
                    <dt className="text-[var(--text-muted)]">{key}</dt>
                    <dd className="text-[var(--text-primary)]">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (section.type === 'prompt_gap_analysis') {
    return (
      <div className="space-y-3">
        {section.data.map((item, index) => (
          <div key={`${item.gapType}-${index}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{item.gapType}</div>
            <div className="mt-1 text-sm text-[var(--text-primary)]">{item.summary}</div>
            <div className="mt-2 text-xs text-[var(--text-muted)]">
              {item.promptSection} · {item.evaluationRule}
            </div>
            {item.suggestedFix && <div className="mt-2 text-sm text-[var(--text-secondary)]">{item.suggestedFix}</div>}
          </div>
        ))}
      </div>
    );
  }

  if (section.type === 'callout') {
    return (
      <CalloutBox variant={calloutVariant(section.data.tone)} title={section.title}>
        {section.data.message}
      </CalloutBox>
    );
  }

  return null;
}

export function PlatformReportView({ report, actions }: { report: PlatformRunReportPayload; actions: ReactNode }) {
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {report.metadata.runName || 'Evaluation Report'}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Generated {new Date(report.metadata.computedAt).toLocaleString()}
          </p>
        </div>
        <div className="shrink-0">{actions}</div>
      </div>

      {report.sections.map((section) => (
        <section key={section.id} className="space-y-4">
          <SectionHeader title={section.title} description={section.description ?? undefined} />
          <SectionContent section={section} />
        </section>
      ))}
    </div>
  );
}

function CrossRunSummaryCard({ summary }: { summary: PlatformCrossRunNarrative }) {
  return (
    <div className="space-y-3">
      <CalloutBox variant="insight" title="AI Cross-Run Summary">
        {summary.executiveSummary}
      </CalloutBox>
      {summary.trendAnalysis && (
        <CalloutBox variant="info" title="Trend Analysis">
          {summary.trendAnalysis}
        </CalloutBox>
      )}
      {summary.criticalPatterns.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {summary.criticalPatterns.map((item, index) => (
            <div key={`${item.title}-${index}`} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
              <div className="font-semibold text-[var(--text-primary)]">{item.title}</div>
              <div className="mt-1 text-sm text-[var(--text-secondary)]">{item.summary}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function PlatformCrossRunDashboard({ appId }: { appId: AppId }) {
  const appConfig = useAppConfig(appId);
  const loadAnalytics = useCrossRunStore((s) => s.loadAnalytics);
  const refreshAnalytics = useCrossRunStore((s) => s.refreshAnalytics);
  const entry = useCrossRunStore((s) => s.entries[appId]);
  const analytics = entry?.data as PlatformCrossRunPayload | null | undefined;

  const [summary, setSummary] = useState<PlatformCrossRunNarrative | null>(null);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const [provider, setProvider] = useState<LLMProvider>(LLM_PROVIDERS[0].value);
  const [model, setModel] = useState('');

  const geminiApiKey = useLLMSettingsStore((s) => s.geminiApiKey);
  const openaiApiKey = useLLMSettingsStore((s) => s.openaiApiKey);
  const azureApiKey = useLLMSettingsStore((s) => s.azureOpenaiApiKey);
  const azureEndpoint = useLLMSettingsStore((s) => s.azureOpenaiEndpoint);
  const anthropicApiKey = useLLMSettingsStore((s) => s.anthropicApiKey);
  const saConfigured = useLLMSettingsStore((s) => s._serviceAccountConfigured);

  const credentialsReady = hasProviderCredentials(provider, {
    geminiApiKey,
    openaiApiKey,
    azureOpenaiApiKey: azureApiKey,
    azureOpenaiEndpoint: azureEndpoint,
    anthropicApiKey,
    _serviceAccountConfigured: saConfigured,
  });

  useEffect(() => {
    void loadAnalytics(appId);
  }, [appId, loadAnalytics]);

  useEffect(() => {
    if (!showModelPicker) return;
    const handleClick = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setShowModelPicker(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showModelPicker]);

  const headerActions = useMemo(() => (
    <div className="flex items-center gap-2">
      <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => void refreshAnalytics(appId)}>
        Refresh
      </Button>
      {appConfig.analytics.capabilities.crossRunAiSummary && (
        <div className="relative" ref={pickerRef}>
          <Button variant="secondary" size="sm" icon={Sparkles} onClick={() => setShowModelPicker((value) => !value)}>
            AI Summary
          </Button>
          {showModelPicker && (
            <div className="absolute right-0 top-full z-30 mt-2 w-80 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-4 shadow-lg">
              <LLMConfigSection
                provider={provider}
                onProviderChange={(value) => { setProvider(value); setModel(''); }}
                model={model}
                onModelChange={setModel}
                compact
              />
              <Button
                variant="primary"
                size="sm"
                icon={Sparkles}
                className="mt-3 w-full"
                disabled={!credentialsReady || !model || generatingSummary}
                onClick={async () => {
                  setGeneratingSummary(true);
                  setShowModelPicker(false);
                  try {
                    const result = await reportsApi.generateCrossRunSummary({
                      appId,
                      provider,
                      model,
                    });
                    setSummary(result);
                  } catch (error) {
                    notificationService.error(error instanceof Error ? error.message : 'Failed to generate AI summary');
                  } finally {
                    setGeneratingSummary(false);
                  }
                }}
              >
                Generate
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  ), [appConfig.analytics.capabilities.crossRunAiSummary, appId, credentialsReady, generatingSummary, model, provider, refreshAnalytics, showModelPicker]);

  if (!entry || entry.status === 'loading') {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--text-muted)]" />
      </div>
    );
  }

  if (!analytics) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No analytics yet"
        description="Generate at least one report, then refresh cross-run analytics."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Dashboard</h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Updated {analytics.metadata.computedAt ? new Date(analytics.metadata.computedAt).toLocaleString() : '—'}
          </p>
        </div>
        {headerActions}
      </div>

      {generatingSummary && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--color-info)]" />
          Generating AI summary...
        </div>
      )}

      {summary && <CrossRunSummaryCard summary={summary} />}

      {analytics.sections.map((section) => (
        <section key={section.id} className="space-y-4">
          <SectionHeader title={section.title} description={section.description ?? undefined} />
          <SectionContent section={section} />
        </section>
      ))}
    </div>
  );
}
