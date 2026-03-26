import { cn } from '@/utils';

interface PasswordRule {
  label: string;
  short: string;
  test: (pw: string) => boolean;
}

const PASSWORD_RULES: PasswordRule[] = [
  { label: 'At least 8 characters', short: '8+ chars', test: (pw) => pw.length >= 8 },
  { label: 'One uppercase letter', short: 'Uppercase', test: (pw) => /[A-Z]/.test(pw) },
  { label: 'One lowercase letter', short: 'Lowercase', test: (pw) => /[a-z]/.test(pw) },
  { label: 'One number', short: 'Number', test: (pw) => /\d/.test(pw) },
  { label: 'One special character', short: 'Special', test: (pw) => /[^A-Za-z0-9]/.test(pw) },
];

export function validatePasswordStrength(password: string): { valid: boolean; passCount: number; total: number } {
  const passCount = PASSWORD_RULES.filter((r) => r.test(password)).length;
  return { valid: passCount === PASSWORD_RULES.length, passCount, total: PASSWORD_RULES.length };
}

interface PasswordStrengthIndicatorProps {
  password: string;
  className?: string;
}

export function PasswordStrengthIndicator({ password, className }: PasswordStrengthIndicatorProps) {
  if (!password) return null;

  const { passCount, total } = validatePasswordStrength(password);
  const strength = passCount / total;

  const strengthLabel =
    strength <= 0.4 ? 'Weak' :
    strength <= 0.6 ? 'Fair' :
    strength < 1 ? 'Good' :
    'Strong';

  const strengthColor =
    strength <= 0.4 ? 'bg-red-500' :
    strength <= 0.6 ? 'bg-orange-500' :
    strength < 1 ? 'bg-yellow-500' :
    'bg-green-500';

  const textColor =
    strength <= 0.4 ? 'text-red-400' :
    strength <= 0.6 ? 'text-orange-400' :
    strength < 1 ? 'text-yellow-400' :
    'text-green-400';

  return (
    <div className={cn('space-y-1.5', className)}>
      {/* Strength bar + label */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 rounded-full bg-[var(--border-subtle)] overflow-hidden">
          <div
            className={cn('h-full rounded-full transition-all duration-300', strengthColor)}
            style={{ width: `${strength * 100}%` }}
          />
        </div>
        <span className={cn('text-[11px] font-medium tabular-nums shrink-0', textColor)}>
          {strengthLabel}
        </span>
      </div>

      {/* Compact inline rule chips */}
      <div className="flex flex-wrap gap-x-1.5 gap-y-1">
        {PASSWORD_RULES.map((rule) => {
          const passed = rule.test(password);
          return (
            <span
              key={rule.label}
              className={cn(
                'inline-flex items-center gap-0.5 rounded-full px-1.5 py-px text-[10px] leading-tight transition-colors',
                passed
                  ? 'bg-green-500/10 text-green-400'
                  : 'bg-[var(--surface-secondary)] text-[var(--text-muted)]',
              )}
            >
              <span className="text-[9px]">{passed ? '\u2713' : '\u2022'}</span>
              {rule.short}
            </span>
          );
        })}
      </div>
    </div>
  );
}
