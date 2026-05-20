import { describe, expect, it, vi } from 'vitest';
import {
  buildNotificationsFormValue,
  EMPTY_NOTIFICATIONS,
  saveNotifications,
  type NotificationsFormValue,
} from '../notificationsForm';

const payload = {
  recipientEmail: 'a@x.com',
  subscriptions: [
    { eventType: 'scheduled_job.failed', group: 'scheduled_job', isActive: true, isRequired: false, recipientEmail: 'a@x.com' },
    { eventType: 'workflow_run.failed', group: 'workflow', isActive: false, isRequired: false, recipientEmail: 'a@x.com' },
  ],
};

describe('buildNotificationsFormValue', () => {
  it('returns an empty slice when no payload has loaded', () => {
    expect(buildNotificationsFormValue(undefined)).toBe(EMPTY_NOTIFICATIONS);
  });

  it('projects the payload preserving subscription order', () => {
    const value = buildNotificationsFormValue(payload);
    expect(value.recipientEmail).toBe('a@x.com');
    expect(value.toggles.map((t) => t.eventType)).toEqual([
      'scheduled_job.failed',
      'workflow_run.failed',
    ]);
  });
});

describe('saveNotifications', () => {
  const store = buildNotificationsFormValue(payload);

  it('only persists toggles that changed', async () => {
    const setActive = vi.fn().mockResolvedValue(undefined);
    const setRecipient = vi.fn().mockResolvedValue(undefined);
    const form: NotificationsFormValue = {
      ...store,
      toggles: store.toggles.map((t) =>
        t.eventType === 'workflow_run.failed' ? { ...t, isActive: true } : t,
      ),
    };
    await saveNotifications(form, store, { setActive, setRecipient });
    expect(setActive).toHaveBeenCalledTimes(1);
    expect(setActive).toHaveBeenCalledWith('workflow_run.failed', true);
    expect(setRecipient).not.toHaveBeenCalled();
  });

  it('persists a changed recipient', async () => {
    const setActive = vi.fn().mockResolvedValue(undefined);
    const setRecipient = vi.fn().mockResolvedValue(undefined);
    await saveNotifications({ ...store, recipientEmail: 'b@x.com' }, store, { setActive, setRecipient });
    expect(setRecipient).toHaveBeenCalledWith('b@x.com');
  });

  it('rejects an invalid recipient before writing', async () => {
    const setActive = vi.fn().mockResolvedValue(undefined);
    const setRecipient = vi.fn().mockResolvedValue(undefined);
    await expect(
      saveNotifications({ ...store, recipientEmail: 'not-an-email' }, store, { setActive, setRecipient }),
    ).rejects.toThrow();
    expect(setRecipient).not.toHaveBeenCalled();
  });
});
