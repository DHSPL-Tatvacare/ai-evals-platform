import { useState, useEffect } from 'react';
import { Modal, Button, Input } from '@/components/ui';
import { rolesApi } from '@/services/api/rolesApi';
import type { RoleResponse, AppResponse } from '@/services/api/rolesApi';
import { notificationService } from '@/services/notifications';
import { cn } from '@/utils';

const PERMISSION_GROUPS = [
  {
    label: 'Listings',
    permissions: [
      { id: 'listing:create', label: 'Create listings' },
      { id: 'listing:delete', label: 'Delete listings' },
    ],
  },
  {
    label: 'Evaluations',
    permissions: [
      { id: 'eval:run', label: 'Run evaluations' },
      { id: 'eval:delete', label: 'Delete / cancel evaluations' },
      { id: 'eval:export', label: 'Export results' },
    ],
  },
  {
    label: 'Resources',
    permissions: [
      { id: 'resource:create', label: 'Create prompts, schemas, evaluators' },
      { id: 'resource:edit', label: 'Edit prompts, schemas, evaluators' },
      { id: 'resource:delete', label: 'Delete prompts, schemas, evaluators' },
    ],
  },
  {
    label: 'Reports & Analytics',
    permissions: [
      { id: 'report:generate', label: 'Generate reports' },
      { id: 'analytics:view', label: 'View analytics dashboards' },
    ],
  },
  {
    label: 'Settings',
    permissions: [{ id: 'settings:edit', label: 'Edit LLM & app settings' }],
  },
  {
    label: 'User Management',
    permissions: [
      { id: 'user:create', label: 'Create users' },
      { id: 'user:invite', label: 'Manage invite links' },
      { id: 'user:edit', label: 'Edit users' },
      { id: 'user:deactivate', label: 'Deactivate users' },
      { id: 'user:reset_password', label: 'Reset passwords' },
      { id: 'role:assign', label: 'Assign roles to users' },
    ],
  },
  {
    label: 'Tenant',
    permissions: [{ id: 'tenant:settings', label: 'Manage tenant settings' }],
  },
];

interface RoleEditorDialogProps {
  isOpen: boolean;
  role: RoleResponse | null;
  onClose: () => void;
  onSaved: () => void;
}

export function RoleEditorDialog({ isOpen, role, onClose, onSaved }: RoleEditorDialogProps) {
  const isEdit = role !== null;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedApps, setSelectedApps] = useState<Set<string>>(new Set());
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set());
  const [apps, setApps] = useState<AppResponse[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    rolesApi.listApps().then(setApps).catch(() => {});
  }, []);

  useEffect(() => {
    if (isOpen) {
      if (role) {
        setName(role.name);
        setDescription(role.description ?? '');
        setSelectedApps(new Set(role.appAccess));
        setSelectedPerms(new Set(role.permissions));
      } else {
        setName('');
        setDescription('');
        setSelectedApps(new Set());
        setSelectedPerms(new Set());
      }
      setError('');
    }
  }, [isOpen, role]);

  const toggleApp = (slug: string) => {
    setSelectedApps((prev) => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
  };

  const togglePerm = (id: string) => {
    setSelectedPerms((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Role name is required');
      return;
    }
    setIsSubmitting(true);
    setError('');
    try {
      const payload = {
        name: name.trim(),
        description: description.trim() || undefined,
        appAccess: Array.from(selectedApps),
        permissions: Array.from(selectedPerms),
      };
      if (isEdit && role) {
        await rolesApi.updateRole(role.id, payload);
        notificationService.success('Role updated');
      } else {
        await rolesApi.createRole(payload);
        notificationService.success('Role created');
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save role');
      notificationService.error('Failed to save role');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={isEdit ? 'Edit Role' : 'Create Role'}>
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Name */}
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Role Name
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Analyst"
            autoFocus
          />
        </div>

        {/* Description */}
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Description <span className="text-[var(--text-muted)]">(optional)</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this role do?"
            rows={2}
            className="w-full rounded-[6px] border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] transition-colors focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50 resize-none"
          />
        </div>

        {/* App Access */}
        {apps.length > 0 && (
          <div>
            <p className="mb-2 text-[13px] font-medium text-[var(--text-secondary)]">App Access</p>
            <div className="flex flex-wrap gap-2">
              {apps.map((app) => {
                const checked = selectedApps.has(app.slug);
                return (
                  <label
                    key={app.slug}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-[12px] transition-colors',
                      checked
                        ? 'border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/10 text-[var(--text-brand)]'
                        : 'border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
                    )}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => toggleApp(app.slug)}
                    />
                    {app.displayName}
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {/* Permissions */}
        <div>
          <p className="mb-3 text-[13px] font-medium text-[var(--text-secondary)]">Permissions</p>
          <div className="space-y-4">
            {PERMISSION_GROUPS.map((group) => (
              <div key={group.label}>
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                  {group.label}
                </p>
                <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {group.permissions.map((perm) => {
                    const checked = selectedPerms.has(perm.id);
                    return (
                      <label
                        key={perm.id}
                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => togglePerm(perm.id)}
                          className="h-3.5 w-3.5 rounded border-[var(--border-default)] accent-[var(--color-brand-accent)]"
                        />
                        {perm.label}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="text-[13px] text-[var(--color-error)]">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="md" isLoading={isSubmitting}>
            {isEdit ? 'Save Changes' : 'Create Role'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
