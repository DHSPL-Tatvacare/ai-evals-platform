/**
 * App-Specific Settings Store
 * Per-app settings that are isolated between Voice Rx and Kaira Bot.
 *
 * Non-sensitive prefs (languageHint, contextWindow, etc.) persist in localStorage.
 * API credentials persist in the backend database via settingsRepository.
 * On startup, Providers.tsx calls loadCredentialsFromBackend() which overwrites
 * any stale localStorage values with the backend's source-of-truth.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { AppId } from '@/types';
import { settingsRepository } from '@/services/api';

// Version to track settings shape changes
const APP_SETTINGS_VERSION = 6; // v6: Added inside-sales app

// Voice Rx specific settings
export interface VoiceRxSettings {
  languageHint: string;
  scriptType: 'auto' | 'devanagari' | 'romanized' | 'original';
  preserveCodeSwitching: boolean;
  // Voice RX transcription API
  voiceRxApiUrl: string;
  voiceRxApiKey: string;
}

// Kaira Bot specific settings
export interface KairaBotSettings {
  contextWindowSize: number;
  maxResponseLength: number;
  historyRetentionDays: number;
  streamResponses: boolean;
  kairaChatUserId: string;
  // Kaira API
  kairaApiUrl: string;
  kairaAuthToken: string;
}

// Inside Sales specific settings (placeholder — no credentials yet)
// eslint-disable-next-line @typescript-eslint/no-empty-object-type
export interface InsideSalesSettings {}

// All app-specific settings
export interface AppSpecificSettings {
  'voice-rx': VoiceRxSettings;
  'kaira-bot': KairaBotSettings;
  'inside-sales': InsideSalesSettings;
}

// New installs start with empty credentials — user must configure via Settings.
const defaultVoiceRxSettings: VoiceRxSettings = {
  languageHint: '',
  scriptType: 'auto',
  preserveCodeSwitching: true,
  voiceRxApiUrl: '',
  voiceRxApiKey: '',
};

const defaultKairaBotSettings: KairaBotSettings = {
  contextWindowSize: 4096,
  maxResponseLength: 2048,
  historyRetentionDays: 30,
  streamResponses: true,
  kairaChatUserId: '',
  kairaApiUrl: '',
  kairaAuthToken: '',
};

interface AppSettingsState {
  _version: number;
  settings: AppSpecificSettings;

  // Voice Rx setters
  updateVoiceRxSettings: (updates: Partial<VoiceRxSettings>) => void;
  resetVoiceRxSettings: () => void;

  // Kaira Bot setters
  updateKairaBotSettings: (updates: Partial<KairaBotSettings>) => void;
  resetKairaBotSettings: () => void;

  // Generic getter
  getAppSettings: <T extends AppId>(appId: T) => AppSpecificSettings[T];

  // Backend persistence for credentials
  loadCredentialsFromBackend: (appId: AppId) => Promise<void>;
  saveCredentialsToBackend: (appId: AppId) => Promise<void>;
  reset: () => void;
}

export const useAppSettingsStore = create<AppSettingsState>()(
  persist(
    (set, get) => ({
      _version: APP_SETTINGS_VERSION,
      settings: {
        'voice-rx': defaultVoiceRxSettings,
        'kaira-bot': defaultKairaBotSettings,
        'inside-sales': {},
      },

      updateVoiceRxSettings: (updates) =>
        set((state) => ({
          settings: {
            ...state.settings,
            'voice-rx': {
              ...state.settings['voice-rx'],
              ...updates,
            },
          },
        })),

      resetVoiceRxSettings: () =>
        set((state) => ({
          settings: {
            ...state.settings,
            'voice-rx': defaultVoiceRxSettings,
          },
        })),

      updateKairaBotSettings: (updates) =>
        set((state) => ({
          settings: {
            ...state.settings,
            'kaira-bot': {
              ...state.settings['kaira-bot'],
              ...updates,
            },
          },
        })),

      resetKairaBotSettings: () =>
        set((state) => ({
          settings: {
            ...state.settings,
            'kaira-bot': defaultKairaBotSettings,
          },
        })),

      getAppSettings: (appId) => get().settings[appId],

      reset: () => set({
        settings: {
          'voice-rx': defaultVoiceRxSettings,
          'kaira-bot': defaultKairaBotSettings,
          'inside-sales': {},
        },
      }),

      /**
       * Load API credentials from the backend settings table.
       * Called on app startup and on settings page mount.
       */
      loadCredentialsFromBackend: async (appId: AppId) => {
        try {
          const data = await settingsRepository.get(appId, 'api-credentials') as Record<string, string> | undefined;
          if (!data) return;

          // Only call set() when values actually differ — avoids creating
          // new object references that trigger downstream re-renders/recomputation.
          const current = get().settings;

          if (appId === 'voice-rx') {
            const cur = current['voice-rx'];
            const newUrl = data.voiceRxApiUrl ?? cur.voiceRxApiUrl;
            const newKey = data.voiceRxApiKey ?? cur.voiceRxApiKey;
            if (newUrl === cur.voiceRxApiUrl && newKey === cur.voiceRxApiKey) return;
            set((state) => ({
              settings: {
                ...state.settings,
                'voice-rx': { ...state.settings['voice-rx'], voiceRxApiUrl: newUrl, voiceRxApiKey: newKey },
              },
            }));
          } else if (appId === 'kaira-bot') {
            const cur = current['kaira-bot'];
            const newUrl = data.kairaApiUrl ?? cur.kairaApiUrl;
            const newToken = data.kairaAuthToken ?? cur.kairaAuthToken;
            const newUserId = data.kairaChatUserId ?? cur.kairaChatUserId;
            if (newUrl === cur.kairaApiUrl && newToken === cur.kairaAuthToken && newUserId === cur.kairaChatUserId) return;
            set((state) => ({
              settings: {
                ...state.settings,
                'kaira-bot': { ...state.settings['kaira-bot'], kairaApiUrl: newUrl, kairaAuthToken: newToken, kairaChatUserId: newUserId },
              },
            }));
          }
        } catch (err) {
          console.error(`[AppSettingsStore] Failed to load ${appId} credentials:`, err);
        }
      },

      /**
       * Save API credentials to the backend settings table.
       * Called from settings pages on save.
       */
      saveCredentialsToBackend: async (appId: AppId) => {
        try {
          const state = get();

          if (appId === 'voice-rx') {
            const s = state.settings['voice-rx'];
            await settingsRepository.set('voice-rx', 'api-credentials', {
              voiceRxApiUrl: s.voiceRxApiUrl,
              voiceRxApiKey: s.voiceRxApiKey,
            });
          } else if (appId === 'kaira-bot') {
            const s = state.settings['kaira-bot'];
            await settingsRepository.set('kaira-bot', 'api-credentials', {
              kairaApiUrl: s.kairaApiUrl,
              kairaAuthToken: s.kairaAuthToken,
              kairaChatUserId: s.kairaChatUserId,
            });
          }
        } catch (err) {
          console.error(`[AppSettingsStore] Failed to save ${appId} credentials:`, err);
          throw err; // Re-throw so the settings page can show an error
        }
      },
    }),
    {
      name: 'app-settings',
      version: APP_SETTINGS_VERSION,
      storage: createJSONStorage(() => localStorage),
      migrate: () => {
        // v6: Added inside-sales app
        return {
          _version: APP_SETTINGS_VERSION,
          settings: {
            'voice-rx': defaultVoiceRxSettings,
            'kaira-bot': defaultKairaBotSettings,
            'inside-sales': {},
          },
        } as AppSettingsState;
      },
      merge: (persistedState, currentState) => {
        const persisted = persistedState as Partial<AppSettingsState>;
        return {
          ...currentState,
          _version: APP_SETTINGS_VERSION,
          settings: {
            'voice-rx': {
              ...currentState.settings['voice-rx'],
              ...persisted.settings?.['voice-rx'],
            },
            'kaira-bot': {
              ...currentState.settings['kaira-bot'],
              ...persisted.settings?.['kaira-bot'],
            },
            'inside-sales': {
              ...currentState.settings['inside-sales'],
              ...persisted.settings?.['inside-sales'],
            },
          },
        };
      },
    }
  )
);

// Convenience hook for Voice Rx settings
export function useVoiceRxSettings() {
  const settings = useAppSettingsStore((state) => state.settings['voice-rx']);
  const updateSettings = useAppSettingsStore((state) => state.updateVoiceRxSettings);
  const resetSettings = useAppSettingsStore((state) => state.resetVoiceRxSettings);
  return { settings, updateSettings, resetSettings };
}

// Convenience hook for Kaira Bot settings
export function useKairaBotSettings() {
  const settings = useAppSettingsStore((state) => state.settings['kaira-bot']);
  const updateSettings = useAppSettingsStore((state) => state.updateKairaBotSettings);
  const resetSettings = useAppSettingsStore((state) => state.resetKairaBotSettings);
  return { settings, updateSettings, resetSettings };
}
