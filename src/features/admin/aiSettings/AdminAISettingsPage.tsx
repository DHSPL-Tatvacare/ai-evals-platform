import { useState } from 'react';
import { Sparkles } from 'lucide-react';

import { PageSurface } from '@/components/ui';
import type { LLMProvider } from '@/services/api/aiSettingsApi';

import { ProviderConfigPanel } from './ProviderConfigPanel';
import { ProviderRail } from './ProviderRail';

export function AdminAISettingsPage() {
  const [selected, setSelected] = useState<LLMProvider>('openai');

  return (
    <PageSurface
      icon={Sparkles}
      title="Model Providers"
      subtitle="Enable providers and configure API keys for AI access"
    >
      <div className="flex h-full min-h-0 gap-4">
        <aside className="w-64 shrink-0 overflow-y-auto">
          <ProviderRail selected={selected} onSelect={setSelected} />
        </aside>
        <section className="flex min-w-0 flex-1 flex-col">
          <ProviderConfigPanel provider={selected} />
        </section>
      </div>
    </PageSurface>
  );
}
