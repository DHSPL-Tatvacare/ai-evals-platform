import type { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { isOwner, isSuperAdmin } from '@/utils/permissions';

type RequireOwnerProps = {
  children: ReactNode;
  /** When true, only super-admins (Owner of SYSTEM_TENANT_ID) pass. */
  superAdmin?: boolean;
};

export function RequireOwner({ children, superAdmin }: RequireOwnerProps) {
  const user = useAuthStore((s) => s.user);
  const allowed = superAdmin ? isSuperAdmin(user) : isOwner(user);
  if (!allowed) {
    return <AccessDenied superAdmin={superAdmin} />;
  }
  return <>{children}</>;
}

function AccessDenied({ superAdmin }: { superAdmin?: boolean }) {
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center">
      <div className="flex max-w-sm flex-col items-center gap-3 rounded-lg border border-dashed border-[var(--border-default)] px-8 py-10 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--surface-info)]">
          <ShieldAlert className="h-5 w-5 text-[var(--text-brand)]" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--text-primary)]">Access restricted</p>
          <p className="text-sm text-[var(--text-secondary)]">
            {superAdmin
              ? 'This surface is available only to super-admins (Owner of the system tenant).'
              : 'This surface is available only to tenant Owners.'}
          </p>
        </div>
      </div>
    </div>
  );
}
