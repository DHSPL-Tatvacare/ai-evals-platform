import { useEffect } from 'react';
import { PieChart } from 'lucide-react';
import { AppTag, ProviderTag } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { ModalityStrip } from '../components/ModalityStrip';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { SpendBreakdownCard } from '../components/SpendBreakdownCard';
import { truncateId } from '../utils/format';
import type { ModalityBreakdown, SpendBundle } from '../types';

interface TabProps {
  active: boolean;
}

export function SpendTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.spend);
  const modalitySlice = useCostStore((s) => s.modality);
  const loadSpend = useCostStore((s) => s.loadSpend);
  const loadModality = useCostStore((s) => s.loadModality);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);

  useEffect(() => {
    if (active) {
      void loadSpend();
      void loadModality();
    }
  }, [active, loadSpend, loadModality, filtersKey]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 pb-6">
      {/* Modality strip — compact, full-width, above the 2×2 grid */}
      <SliceStateBoundary
        slice={modalitySlice}
        onRetry={() => refresh('modality')}
        loadingLabel="Loading modality…"
      >
        {(data: ModalityBreakdown) => <ModalityStrip data={data} />}
      </SliceStateBoundary>

      {/* 2×2 spend breakdown grid */}
      <div className="flex min-h-0 flex-1 flex-col">
        <SliceStateBoundary
          slice={slice}
          onRetry={() => refresh('spend')}
          emptyIcon={PieChart}
          emptyTitle="No spend"
          emptyDescription="No LLM spend was recorded for the selected range."
          isEmpty={(data) =>
            data.byApp.length === 0 &&
            data.byPurpose.length === 0 &&
            data.topModels.length === 0 &&
            data.topUsers.length === 0
          }
        >
          {(data) => <SpendContent data={data} />}
        </SliceStateBoundary>
      </div>
    </div>
  );
}

function SpendContent({ data }: { data: SpendBundle }) {
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-2 lg:grid-rows-2">
      <SpendBreakdownCard
        title="By app"
        subtitle="by cost"
        rows={data.byApp}
        nameHeader="App"
        renderName={(row) => <AppTag value={row.key} />}
        searchPlaceholder="Search apps"
      />
      <SpendBreakdownCard
        title="By purpose"
        subtitle="by cost"
        rows={data.byPurpose}
        nameHeader="Purpose"
        renderName={(row) => <span className="text-[var(--text-secondary)]">{row.key}</span>}
        searchPlaceholder="Search purposes"
      />
      <SpendBreakdownCard
        title="Top models"
        subtitle="by cost"
        rows={data.topModels}
        nameHeader="Model"
        renderName={(row) => (
          <span className="flex min-w-0 items-center gap-2">
            <ProviderTag value={providerOf(row.key)} />
            <span className="truncate font-mono" title={row.key}>
              {row.key}
            </span>
          </span>
        )}
        searchPlaceholder="Search models"
      />
      <SpendBreakdownCard
        title="Top users"
        subtitle="by cost"
        rows={data.topUsers}
        nameHeader="User"
        renderName={(row) => (
          <span className="truncate font-mono" title={row.key}>
            {truncateId(row.key, 8)}
          </span>
        )}
        searchPlaceholder="Search users"
      />
    </div>
  );
}

function providerOf(model: string): string {
  const lower = model.toLowerCase();
  if (lower.includes('claude')) return 'anthropic';
  if (lower.includes('gemini')) return 'gemini';
  if (lower.includes('gpt') || lower.includes('o1') || lower.includes('o3')) return 'openai';
  return '—';
}
