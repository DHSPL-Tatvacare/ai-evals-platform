import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

export function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);

  if (!user || (user.role !== 'admin' && user.role !== 'owner')) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
