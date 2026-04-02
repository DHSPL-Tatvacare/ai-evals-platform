import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { appsRepository } from '@/services/api/appsApi';
import { APP_CONFIG_FALLBACKS, DEFAULT_APP, mergeAppConfig, type AppConfig, type AppId } from '@/types';

interface AppStoreState {
  currentApp: AppId;
  appConfigs: Record<AppId, AppConfig>;
  setCurrentApp: (app: AppId) => void;
  setAppConfig: (app: AppId, config: AppConfig) => void;
  setAppConfigs: (configs: Partial<Record<AppId, AppConfig>>) => void;
  getAppConfig: (app: AppId) => AppConfig;
  loadAppConfig: (app: AppId) => Promise<void>;
  loadAppConfigs: (apps: AppId[]) => Promise<void>;
  reset: () => void;
}

export const useAppStore = create<AppStoreState>()(
  persist(
    (set, get) => ({
      currentApp: DEFAULT_APP,
      appConfigs: APP_CONFIG_FALLBACKS,
      setCurrentApp: (app) => set({ currentApp: app }),
      setAppConfig: (app, config) =>
        set((state) => ({
          appConfigs: {
            ...state.appConfigs,
            [app]: mergeAppConfig(app, config),
          },
        })),
      setAppConfigs: (configs) =>
        set((state) => {
          const nextConfigs: Record<AppId, AppConfig> = { ...state.appConfigs };
          (Object.keys(configs) as AppId[]).forEach((app) => {
            const config = configs[app];
            if (config) {
              nextConfigs[app] = mergeAppConfig(app, config);
            }
          });
          return { appConfigs: nextConfigs };
        }),
      getAppConfig: (app) => get().appConfigs[app] ?? APP_CONFIG_FALLBACKS[app],
      loadAppConfig: async (app) => {
        try {
          const config = await appsRepository.getConfig(app);
          get().setAppConfig(app, config);
        } catch {
          // Keep fallback config if the backend config is unavailable.
        }
      },
      loadAppConfigs: async (apps) => {
        const uniqueApps = [...new Set(apps)] as AppId[];
        if (uniqueApps.length === 0) {
          return;
        }

        const results = await Promise.allSettled(
          uniqueApps.map(async (app) => ({
            app,
            config: await appsRepository.getConfig(app),
          })),
        );

        const nextConfigs: Partial<Record<AppId, AppConfig>> = {};
        results.forEach((result) => {
          if (result.status === 'fulfilled') {
            nextConfigs[result.value.app] = result.value.config;
          }
        });

        if (Object.keys(nextConfigs).length > 0) {
          get().setAppConfigs(nextConfigs);
        }
      },
      reset: () => set({ currentApp: DEFAULT_APP, appConfigs: APP_CONFIG_FALLBACKS }),
    }),
    {
      name: 'app-selection',
      partialize: (state) => ({
        currentApp: state.currentApp,
      }),
    }
  )
);

// Re-export AppId for convenience
export type { AppId };
