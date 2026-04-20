import type { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { userHasPermission } from '@/utils/permissions';

interface RequirePermissionProps {
  action: string;
  children: ReactNode;
}

/** Route-level permission gate. Renders <AccessDenied/> in place (no redirect)
 *  when the user lacks the permission, so back/forward navigation stays
 *  intact. Owners bypass permission checks via `userHasPermission`. */
export function RequirePermission({ action, children }: RequirePermissionProps) {
  const user = useAuthStore((s) => s.user);
  if (!userHasPermission(user, action)) {
    return <AccessDenied action={action} />;
  }
  return <>{children}</>;
}

function AccessDenied({ action }: { action: string }) {
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center">
      <div className="flex max-w-sm flex-col items-center gap-3 rounded-lg border border-dashed border-[var(--border-default)] px-8 py-10 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--surface-info)]">
          <ShieldAlert className="h-5 w-5 text-[var(--text-brand)]" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--text-primary)]">Access restricted</p>
          <p className="text-sm text-[var(--text-secondary)]">
            This surface requires the <code className="font-mono text-[12px]">{action}</code>{' '}
            permission. Ask an Owner to grant it via role management.
          </p>
        </div>
      </div>
    </div>
  );
}
