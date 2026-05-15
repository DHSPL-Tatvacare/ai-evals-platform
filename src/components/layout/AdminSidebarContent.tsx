import { Fragment } from 'react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/utils';
import type { SidebarNavGroup } from '@/config/sidebarNav';

interface AdminSidebarContentProps {
  groups: SidebarNavGroup[];
}

/**
 * Renders the admin nav as labelled sections. Group order, titles, and
 * items all come from `getAdminNavGroups` — this component is a pure
 * projection. Empty groups are filtered upstream so we never need to
 * reason about them here.
 */
export function AdminSidebarContent({ groups }: AdminSidebarContentProps) {
  return (
    <nav className="flex flex-col gap-3 px-2 py-2">
      {groups.map((group, groupIdx) => (
        <Fragment key={group.id}>
          <div className="flex flex-col">
            <div
              className={cn(
                'px-3 pb-1.5 text-[10.5px] font-medium uppercase tracking-wide text-[var(--text-muted)]',
                groupIdx === 0 && 'pt-0',
              )}
            >
              {group.title}
            </div>
            <div className="flex flex-col gap-0.5">
              {group.items.map(({ to, icon: Icon, label, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 rounded-[6px] px-3 py-2 text-[13px] font-medium transition-colors',
                      isActive
                        ? 'bg-[var(--color-brand-accent)]/20 text-[var(--text-brand)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]',
                    )
                  }
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        </Fragment>
      ))}
    </nav>
  );
}
