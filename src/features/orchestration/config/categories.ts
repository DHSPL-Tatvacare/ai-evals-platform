import {
  Database,
  Filter,
  GitBranch,
  Send,
  AlertTriangle,
  CheckCircle2,
  type LucideIcon,
} from 'lucide-react';

import type { NodeCategory } from '@/features/orchestration/types';

export interface NodeCategoryDef {
  label: string;
  icon: LucideIcon;
  /** Soft panel background for the category bar (light + dark via tokens). */
  surfaceVar: string;
  /** Solid fill for the icon square inside the category bar. */
  iconBgVar: string;
  /** Foreground / accent — used for category text + node border. */
  accentVar: string;
}

export const NODE_CATEGORIES: Record<NodeCategory, NodeCategoryDef> = {
  source: {
    label: 'Source',
    icon: Database,
    surfaceVar: 'var(--surface-success)',
    iconBgVar: 'var(--color-success)',
    accentVar: 'var(--color-success)',
  },
  filter: {
    label: 'Filter',
    icon: Filter,
    surfaceVar: 'var(--surface-success)',
    iconBgVar: 'var(--color-success)',
    accentVar: 'var(--color-success)',
  },
  logic: {
    label: 'Logic',
    icon: GitBranch,
    surfaceVar: 'var(--surface-warning)',
    iconBgVar: 'var(--color-warning)',
    accentVar: 'var(--color-warning)',
  },
  action: {
    label: 'Action',
    icon: Send,
    surfaceVar: 'var(--surface-info)',
    iconBgVar: 'var(--color-info)',
    accentVar: 'var(--color-info)',
  },
  escalation: {
    label: 'Escalation',
    icon: AlertTriangle,
    surfaceVar: 'var(--surface-error)',
    iconBgVar: 'var(--color-error)',
    accentVar: 'var(--color-error)',
  },
  sink: {
    label: 'Sink',
    icon: CheckCircle2,
    surfaceVar: 'var(--bg-tertiary)',
    iconBgVar: 'var(--text-muted)',
    accentVar: 'var(--text-secondary)',
  },
};

export function getCategoryDef(category: string): NodeCategoryDef {
  return NODE_CATEGORIES[category as NodeCategory] ?? NODE_CATEGORIES.logic;
}
