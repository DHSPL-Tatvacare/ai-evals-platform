import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { Button } from '@/components/ui';
import { routes } from '@/config/routes';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const canSubmit = email.trim().length > 0 && password.length > 0 && !isLoading;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setIsLoading(true);
    setError('');
    try {
      await login({ email, password });
      navigate(routes.voiceRx.home);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('Email domain not allowed')) {
        setError(msg);
      } else {
        setError('Invalid email or password. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-primary)] bg-cover bg-center bg-no-repeat" style={{ backgroundImage: 'url(/primary_background.svg)' }}>
      <div className="w-full max-w-[400px] rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-8 shadow-lg">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-4">
          <div className="rounded-lg bg-white px-5 py-2.5">
            <img
              src="/tatvacare-logo.svg"
              alt="Tatvacare"
              className="h-8 w-auto"
            />
          </div>
          <div className="text-center">
            <h1 className="text-lg font-semibold text-[var(--text-primary)]">
              AI Evals Platform
            </h1>
            <p className="mt-1 text-[13px] text-[var(--text-muted)]">
              Sign in to your account
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-[13px] text-red-400">
              {error}
            </div>
          )}

          <div>
            <label
              htmlFor="email"
              className="mb-1.5 block text-[13px] font-medium text-[var(--text-secondary)]"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2.5 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--color-brand-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)] transition-colors"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-1.5 block text-[13px] font-medium text-[var(--text-secondary)]"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2.5 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--color-brand-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)] transition-colors"
              placeholder="Enter your password"
            />
          </div>

          <Button
            type="submit"
            size="lg"
            disabled={!canSubmit}
            isLoading={isLoading}
            className="mt-2 w-full"
          >
            {isLoading ? 'Signing in...' : 'Sign in'}
          </Button>
        </form>
      </div>
    </div>
  );
}
