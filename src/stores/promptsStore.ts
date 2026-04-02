import { create } from "zustand";
import type { PromptDefinition, AppId, ListingSourceType } from "@/types";
import type { AssetVisibility } from "@/types/settings.types";
import { promptsRepository } from "@/services/storage";

interface PromptsState {
  // Prompts keyed by appId
  prompts: Record<AppId, PromptDefinition[]>;
  isLoading: boolean;
  error: string | null;

  loadPrompts: (
    appId: AppId,
    promptType?: PromptDefinition["promptType"],
    opts?: { branchKey?: string; latestOnly?: boolean; visibility?: AssetVisibility },
  ) => Promise<void>;
  getPrompt: (appId: AppId, id: string) => PromptDefinition | undefined;
  getPromptsByType: (
    appId: AppId,
    promptType: PromptDefinition["promptType"],
    sourceType?: ListingSourceType,
    visibility?: AssetVisibility,
  ) => PromptDefinition[];
  getPromptsByVisibility: (appId: AppId, visibility: AssetVisibility) => PromptDefinition[];
  savePrompt: (
    appId: AppId,
    prompt: Partial<PromptDefinition> & {
      promptType: PromptDefinition["promptType"];
      prompt: string;
    },
  ) => Promise<PromptDefinition>;
  deletePrompt: (appId: AppId, id: string) => Promise<void>;
  reset: () => void;
}

function replaceById<T extends { id: string }>(items: T[], item: T): T[] {
  const index = items.findIndex((entry) => entry.id === item.id);
  if (index === -1) {
    return [item, ...items];
  }
  return items.map((entry) => (entry.id === item.id ? item : entry));
}

function removeById<T extends { id: string }>(items: T[], id: string): T[] {
  return items.filter((item) => item.id !== id);
}

function upsertPrompt(items: PromptDefinition[], prompt: PromptDefinition): PromptDefinition[] {
  const sameId = items.some((entry) => entry.id === prompt.id);
  if (sameId) {
    return replaceById(items, prompt);
  }
  if (prompt.branchKey) {
    return [prompt, ...items.filter((entry) => entry.branchKey !== prompt.branchKey)];
  }
  return [prompt, ...items];
}

export const usePromptsStore = create<PromptsState>((set, get) => ({
  prompts: {
    "voice-rx": [],
    "kaira-bot": [],
    "inside-sales": [],
  },
  isLoading: false,
  error: null,

  loadPrompts: async (appId, promptType, opts) => {
    set({ isLoading: true, error: null });
    try {
      const prompts = await promptsRepository.getAll(appId, promptType, opts);
      set((state) => ({
        prompts: {
          ...state.prompts,
          [appId]: prompts,
        },
        isLoading: false,
      }));
    } catch (err) {
      console.error("[PromptsStore] Failed to load prompts:", err);
      set({
        error: err instanceof Error ? err.message : "Failed to load prompts",
        isLoading: false,
      });
    }
  },

  getPrompt: (appId, id) => {
    return (get().prompts[appId] || []).find((p) => p.id === id);
  },

  getPromptsByType: (appId, promptType, sourceType, visibility) => {
    return (get().prompts[appId] || []).filter((p) => {
      if (p.promptType !== promptType) return false;
      if (visibility && p.visibility !== visibility) return false;
      if (sourceType) {
        return p.sourceType === sourceType || !p.sourceType;
      }
      return true;
    });
  },

  getPromptsByVisibility: (appId, visibility) => {
    return (get().prompts[appId] || []).filter((prompt) => prompt.visibility === visibility);
  },

  savePrompt: async (appId, promptData) => {
    set({ isLoading: true, error: null });
    try {
      const saved = await promptsRepository.save(
        appId,
        promptData as PromptDefinition,
      );
      set((state) => ({
        prompts: {
          ...state.prompts,
          [appId]: upsertPrompt(state.prompts[appId] || [], saved),
        },
        isLoading: false,
      }));
      return saved;
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to save prompt",
        isLoading: false,
      });
      throw err;
    }
  },

  deletePrompt: async (appId, id) => {
    set({ isLoading: true, error: null });
    try {
      await promptsRepository.delete(appId, id);
      set((state) => ({
        prompts: {
          ...state.prompts,
          [appId]: removeById(state.prompts[appId] || [], id),
        },
        isLoading: false,
      }));
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : "Failed to delete prompt",
        isLoading: false,
      });
      throw err;
    }
  },

  reset: () =>
    set({
      prompts: { "voice-rx": [], "kaira-bot": [], "inside-sales": [] },
      isLoading: false,
      error: null,
    }),
}));
