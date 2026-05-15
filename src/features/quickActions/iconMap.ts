/**
 * Icon name → Lucide component map.
 *
 * Quick-action specs reference icons by string (e.g. ``"MessageSquare"``)
 * because the spec list comes from the DB-backed app config — strings are
 * what survives JSON serialization. This map resolves those strings to
 * Lucide React components at render time. Unknown / missing names fall back
 * to a neutral `Plus` glyph so a misconfigured spec still renders.
 *
 * Add new icons here as needed; keep the set small and intentional rather
 * than re-exporting all of lucide-react (every entry adds to the bundle).
 */
import type { LucideIcon } from 'lucide-react';
import {
  FileAudio,
  FileSpreadsheet,
  MessageSquare,
  Plus,
  ShieldAlert,
  Workflow,
  Zap,
} from 'lucide-react';

export const QUICK_ACTION_ICONS: Record<string, LucideIcon> = {
  FileAudio,
  FileSpreadsheet,
  MessageSquare,
  Plus,
  ShieldAlert,
  Workflow,
  Zap,
};

export function resolveQuickActionIcon(name: string | undefined): LucideIcon {
  if (!name) return Plus;
  return QUICK_ACTION_ICONS[name] ?? Plus;
}
