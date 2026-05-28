import { SegmentedControl } from './SegmentedControl';

export type AnalyticsScope = 'mine' | 'tenant';

interface ScopeToggleProps {
  value: AnalyticsScope;
  onChange: (value: AnalyticsScope) => void;
  /** Render the tenant-wide option only when the caller is admin-authorized.
   *  The server re-validates; this just hides an option the user can't use. */
  canSeeTenant: boolean;
  disabled?: boolean;
  className?: string;
}

/** Analytics scope switch. "My campaigns" (owned + shared) is always available;
 *  "All campaigns" (tenant-wide) appears only for admin-authorized callers. */
export function ScopeToggle({ value, onChange, canSeeTenant, disabled, className }: ScopeToggleProps) {
  const options: { value: AnalyticsScope; label: string }[] = [
    { value: 'mine', label: 'My campaigns' },
    ...(canSeeTenant ? [{ value: 'tenant' as const, label: 'All campaigns' }] : []),
  ];

  return (
    <SegmentedControl
      options={options}
      value={value}
      onChange={onChange}
      disabled={disabled}
      className={className}
      aria-label="Analytics scope"
    />
  );
}
