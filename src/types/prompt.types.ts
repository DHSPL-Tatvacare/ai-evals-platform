import type { AssetVisibility } from './settings.types';

export interface PromptDefinition {
  id: string;
  userId?: string;
  tenantId?: string;
  name: string;                    // Auto-generated: "Evaluation Prompt v3"
  version: number;                 // Auto-increment per promptType
  branchKey?: string;               // Versioned library branch identifier
  visibility?: AssetVisibility;     // Sharing scope
  forkedFrom?: number | null;      // ID of parent prompt if forked
  sharedBy?: string | null;        // User who shared this prompt
  sharedAt?: string | null;        // ISO timestamp when shared
  createdAt: Date;
  updatedAt: Date;
  promptType: 'transcription' | 'evaluation' | 'extraction';
  prompt: string;                  // The actual prompt text
  description?: string;
  isDefault?: boolean;             // Mark built-in prompts
  sourceType?: 'upload' | 'api' | null;  // Flow type (upload or api)
}

export interface PromptReference {
  id: string;
  name: string;
  version: number;
}
