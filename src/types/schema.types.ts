import type { AssetVisibility } from './settings.types';

export interface SchemaDefinition {
  id: string;
  userId?: string;
  tenantId?: string;
  name: string;                    // Auto-generated: "Evaluation Schema v3"
  version: number;                 // Auto-increment per promptType
  branchKey?: string;               // Versioned library branch identifier
  visibility?: AssetVisibility;     // Sharing scope
  forkedFrom?: number | null;      // ID of parent schema if forked
  sharedBy?: string | null;        // User who shared this schema
  sharedAt?: string | null;        // ISO timestamp when shared
  createdAt: Date;
  updatedAt: Date;
  promptType: 'transcription' | 'evaluation' | 'extraction';
  schema: Record<string, unknown>; // JSON Schema object
  description?: string;
  isDefault?: boolean;             // Mark built-in schemas
  sourceType?: 'upload' | 'api' | null; // Flow type (upload or api)
}

export interface SchemaReference {
  id: string;
  name: string;
  version: number;
}
