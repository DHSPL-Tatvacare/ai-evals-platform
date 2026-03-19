import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Button, PasswordStrengthIndicator, validatePasswordStrength } from '@/components/ui';
import { useAuthStore } from '@/stores/authStore';
import { authApi } from '@/services/api/authApi';
import { routes } from '@/config/routes';
import type { ValidateInviteResult } from '@/types/auth.types';

function isEmailDomainAllowed(email: string, allowedDomains: string[]): boolean {
  if (!allowedDomains.length) return true;
  const lower = email.trim().toLowerCase();
  return allowedDomains.some((d) => lower.endsWith(d.toLowerCase()));
}

export function SignupPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('invite') ?? '';
  const navigate = useNavigate();

  const [isValidating, setIsValidating] = useState(true);
  const [inviteInfo, setInviteInfo] = useState<ValidateInviteResult | null>(null);
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const allowedDomains = inviteInfo?.allowedDomains ?? [];

  useEffect(() => {
    if (!token) {
      setIsValidating(false);
      return;
    }
    authApi.validateInvite(token).then((result) => {
      setInviteInfo(result);
      setIsValidating(false);
    }).catch(() => {
      setIsValidating(false);
    });
  }, [token]);

  const emailDomainValid = !email.trim() || isEmailDomainAllowed(email, allowedDomains);
  const { valid: passwordStrong } = validatePasswordStrength(password);

  const canSubmit =
    email.trim().length > 0 &&
    displayName.trim().length > 0 &&
    passwordStrong &&
    password === confirmPassword &&
    emailDomainValid &&
    !isSubmitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    if (!emailDomainValid) {
      setError(`Email must be from: ${allowedDomains.join(', ')}`);
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (!passwordStrong) {
      setError('Password does not meet strength requirements');
      return;
    }

    setIsSubmitting(true);
    setError('');
    try {
      const result = await authApi.signup({
        token,
        email: email.trim(),
        password,
        displayName: displayName.trim(),
      });
      // Log in immediately with the returned token
      useAuthStore.getState().setAccessToken(result.accessToken);
      // Reload user to populate store
      await useAuthStore.getState().loadUser();
      navigate(routes.voiceRx.home);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const isInvalid = !isValidating && (!token || !inviteInfo?.valid);

  const inputClass =
    'w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2.5 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--color-brand-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)] transition-colors';

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-primary)] bg-cover bg-center bg-no-repeat" style={{ backgroundImage: 'url(/primary_background.svg)' }}>
      <div className="w-full max-w-[420px] rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-8 shadow-lg">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-4">
          <div className="rounded-lg bg-white px-5 py-2.5">
            <img src="/tatvacare-logo.svg" alt="Tatvacare" className="h-8 w-auto" />
          </div>
        </div>

        {isValidating && (
          <div className="py-12 text-center text-[13px] text-[var(--text-muted)]">
            Validating invite link...
          </div>
        )}

        {isInvalid && (
          <div className="text-center">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Invalid Invite Link
            </h2>
            <p className="mt-2 text-[13px] text-[var(--text-muted)]">
              This invite link is invalid, expired, or has reached its usage limit.
            </p>
            <Link
              to={routes.login}
              className="mt-4 inline-block text-[13px] font-medium text-[var(--text-brand)] hover:underline"
            >
              Go to Sign In
            </Link>
          </div>
        )}

        {!isValidating && inviteInfo?.valid && (
          <>
            <div className="mb-6 text-center">
              <h1 className="text-lg font-semibold text-[var(--text-primary)]">
                Create your account
              </h1>
              <p className="mt-1 text-[13px] text-[var(--text-muted)]">
                You&apos;ve been invited to join{' '}
                <span className="font-medium text-[var(--text-primary)]">
                  {inviteInfo.tenantName}
                </span>
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-[13px] text-red-400">
                  {error}
                </div>
              )}

              <div>
                <label htmlFor="displayName" className="mb-1.5 block text-[13px] font-medium text-[var(--text-secondary)]">
                  Full Name
                </label>
                <input
                  id="displayName"
                  type="text"
                  required
                  autoFocus
                  autoComplete="name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className={inputClass}
                  placeholder="John Doe"
                />
              </div>

              <div>
                <label htmlFor="email" className="mb-1.5 block text-[13px] font-medium text-[var(--text-secondary)]">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputClass}
                  placeholder={allowedDomains.length ? `you${allowedDomains[0]}` : 'you@example.com'}
                />
                {allowedDomains.length > 0 && (
                  <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                    Only {allowedDomains.join(', ')} emails are allowed
                  </p>
                )}
                {email.trim() && !emailDomainValid && (
                  <p className="mt-1 text-[11px] text-red-400">
                    Email must be from: {allowedDomains.join(', ')}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-[13px] font-medium text-[var(--text-secondary)]">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputClass}
                  placeholder="Create a strong password"
                />
                <PasswordStrengthIndicator password={password} className="mt-2" />
              </div>

              <div>
                <label htmlFor="confirmPassword" className="mb-1.5 block text-[13px] font-medium text-[var(--text-secondary)]">
                  Confirm Password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className={inputClass}
                  placeholder="Re-enter your password"
                />
                {confirmPassword.length > 0 && password !== confirmPassword && (
                  <p className="mt-1 text-[11px] text-red-400">Passwords do not match</p>
                )}
              </div>

              <Button
                type="submit"
                size="lg"
                disabled={!canSubmit}
                isLoading={isSubmitting}
                className="mt-2 w-full"
              >
                {isSubmitting ? 'Creating account...' : 'Create Account'}
              </Button>
            </form>

            <p className="mt-4 text-center text-[12px] text-[var(--text-muted)]">
              Already have an account?{' '}
              <Link to={routes.login} className="font-medium text-[var(--text-brand)] hover:underline">
                Sign in
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
