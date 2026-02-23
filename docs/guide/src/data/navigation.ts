import type { ComponentType } from 'react';

export interface NavItem {
  id: string;
  label: string;
  icon: string; // lucide icon name
}

export const navigation: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: 'Layout' },
  { id: 'workflows', label: 'Workflows', icon: 'GitBranch' },
  { id: 'api-auth', label: 'API & Auth', icon: 'Key' },
  { id: 'prompts-schemas', label: 'Prompts & Schemas', icon: 'FileText' },
  { id: 'pipelines', label: 'Pipelines', icon: 'Workflow' },
  { id: 'brain-map', label: 'Brain Map', icon: 'Brain' },
  { id: 'db-api-ref', label: 'DB & API Ref', icon: 'Database' },
  { id: 'sbom', label: 'SBOM', icon: 'Package' },
  { id: 'api-explorer', label: 'API Explorer', icon: 'Terminal' },
];

export interface PageDef {
  id: string;
  component: ComponentType;
}
