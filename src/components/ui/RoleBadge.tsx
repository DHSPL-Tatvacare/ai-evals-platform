import { Badge } from './Badge';
import type { FieldRole } from '@/types';

interface RoleBadgeProps {
  role: FieldRole;
}

export function RoleBadge({ role }: RoleBadgeProps) {
  if (role === 'metric') {
    return <Badge variant="success">Metric</Badge>;
  }
  if (role === 'reasoning') {
    return <Badge variant="warning">Reasoning</Badge>;
  }
  return <Badge variant="neutral">Detail</Badge>;
}
