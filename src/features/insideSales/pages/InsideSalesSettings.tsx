import { Card } from '@/components/ui';
import { SettingsPanel } from '@/features/settings/components/SettingsPanel';
import { getGlobalSettingsByCategory } from '@/features/settings/schemas/globalSettingsSchema';
import { useGlobalSettingsStore } from '@/stores';

export function InsideSalesSettings() {
  const theme = useGlobalSettingsStore((s) => s.theme);
  const setTheme = useGlobalSettingsStore((s) => s.setTheme);

  const formValues = { theme };
  const handleChange = (key: string, value: unknown) => {
    if (key === 'theme') setTheme(value as typeof theme);
  };

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Settings</h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">Inside Sales app configuration</p>
      </div>

      <Card>
        <SettingsPanel
          settings={getGlobalSettingsByCategory('appearance')}
          values={formValues}
          onChange={handleChange}
        />
      </Card>
    </div>
  );
}
