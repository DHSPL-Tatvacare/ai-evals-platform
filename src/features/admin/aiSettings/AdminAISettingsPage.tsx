import { useState } from 'react';
import { Sparkles } from 'lucide-react';

import { PageSurface } from '@/components/ui';
import type { LLMProvider } from '@/services/api/aiSettingsApi';

import { ProviderRail } from './ProviderRail';

function ProviderConfigPlaceholder({ provider }: { provider: LLMProvider }) {
  return (
    <div className="rounded-md border border-dashed border-[var(--border-default)] bg-[var(--bg-secondary)] p-6 text-sm text-[var(--text-secondary)]">
      Select &quot;{provider}&quot; config &mdash; panel arrives in Task 8.
    </div>
  );
}

export function AdminAISettingsPage() {
  const [selected, setSelected] = useState<LLMProvider>('openai');

  return (
    <PageSurface
      icon={Sparkles}
      title="Model Providers"
      subtitle="Enable providers and configure API keys for AI access"
    >
      <div className="flex h-full min-h-0 gap-4">
        <aside className="w-64 shrink-0">
          <ProviderRail selected={selected} onSelect={setSelected} />
        </aside>
        <section className="min-w-0 flex-1 overflow-y-auto">
          <ProviderConfigPlaceholder provider={selected} />
        </section>
      </div>
    </PageSurface>
  );
}
