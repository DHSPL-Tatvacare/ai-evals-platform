import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';
import { Button } from '@/components/ui';
import { useAuthStore } from '@/stores/authStore';
import { firstAccessibleRoute } from '@/config/routes';

export function NotFoundPage() {
  const user = useAuthStore((state) => state.user);
  const homePath = firstAccessibleRoute(user?.appAccess ?? []);

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center text-center">
      <h1 className="text-6xl font-bold text-[var(--text-muted)]">404</h1>
      <p className="mt-4 text-lg text-[var(--text-secondary)]">Page not found</p>
      <Link to={homePath} className="mt-6">
        <Button variant="secondary">
          <Home className="h-4 w-4" />
          Go Home
        </Button>
      </Link>
    </div>
  );
}
