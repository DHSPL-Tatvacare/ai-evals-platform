import { create } from 'zustand';
import type { SchemaDefinition, AppId, ListingSourceType } from '@/types';
import type { AssetVisibility } from '@/types/settings.types';
import { schemasRepository } from '@/services/storage';

interface SchemasState {
  // Schemas keyed by appId
  schemas: Record<AppId, SchemaDefinition[]>;
  isLoading: boolean;
  error: string | null;

  loadSchemas: (appId: AppId, promptType?: SchemaDefinition['promptType'], opts?: { branchKey?: string; latestOnly?: boolean; visibility?: AssetVisibility }) => Promise<void>;
  getSchema: (appId: AppId, id: string) => SchemaDefinition | undefined;
  getSchemasByType: (appId: AppId, promptType: SchemaDefinition['promptType'], sourceType?: ListingSourceType, visibility?: AssetVisibility) => SchemaDefinition[];
  getSchemasByVisibility: (appId: AppId, visibility: AssetVisibility) => SchemaDefinition[];
  saveSchema: (appId: AppId, schema: Partial<SchemaDefinition> & { promptType: SchemaDefinition['promptType']; schema: Record<string, unknown> }) => Promise<SchemaDefinition>;
  deleteSchema: (appId: AppId, id: string) => Promise<void>;
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

function upsertSchema(items: SchemaDefinition[], schema: SchemaDefinition): SchemaDefinition[] {
  const sameId = items.some((entry) => entry.id === schema.id);
  if (sameId) {
    return replaceById(items, schema);
  }
  if (schema.branchKey) {
    return [schema, ...items.filter((entry) => entry.branchKey !== schema.branchKey)];
  }
  return [schema, ...items];
}

export const useSchemasStore = create<SchemasState>((set, get) => ({
  schemas: {
    'voice-rx': [],
    'kaira-bot': [],
    'inside-sales': [],
  },
  isLoading: false,
  error: null,

  loadSchemas: async (appId, promptType, opts) => {
    set({ isLoading: true, error: null });
    try {
      const schemas = await schemasRepository.getAll(appId, promptType, opts);
      set((state) => ({ 
        schemas: {
          ...state.schemas,
          [appId]: schemas,
        },
        isLoading: false,
      }));
    } catch (err) {
      console.error('[SchemasStore] Failed to load schemas:', err);
      set({ error: err instanceof Error ? err.message : 'Failed to load schemas', isLoading: false });
    }
  },

  getSchema: (appId, id) => {
    return (get().schemas[appId] || []).find(s => s.id === id);
  },

  getSchemasByType: (appId, promptType, sourceType, visibility) => {
    return (get().schemas[appId] || []).filter(s => {
      if (s.promptType !== promptType) return false;
      if (visibility && s.visibility !== visibility) return false;
      if (sourceType) {
        return s.sourceType === sourceType || !s.sourceType;
      }
      return true;
    });
  },

  getSchemasByVisibility: (appId, visibility) => {
    return (get().schemas[appId] || []).filter((schema) => schema.visibility === visibility);
  },

  saveSchema: async (appId, schemaData) => {
    set({ isLoading: true, error: null });
    try {
      const saved = await schemasRepository.save(appId, schemaData as SchemaDefinition);
      set(state => ({
        schemas: {
          ...state.schemas,
          [appId]: upsertSchema(state.schemas[appId] || [], saved),
        },
        isLoading: false,
      }));
      return saved;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to save schema', isLoading: false });
      throw err;
    }
  },

  deleteSchema: async (appId, id) => {
    set({ isLoading: true, error: null });
    try {
      await schemasRepository.delete(appId, id);
      set(state => ({
        schemas: {
          ...state.schemas,
          [appId]: removeById(state.schemas[appId] || [], id),
        },
        isLoading: false,
      }));
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to delete schema', isLoading: false });
      throw err;
    }
  },

  reset: () => set({
    schemas: { 'voice-rx': [], 'kaira-bot': [], 'inside-sales': [] },
    isLoading: false,
    error: null,
  }),
}));
