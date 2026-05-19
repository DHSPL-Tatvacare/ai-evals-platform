/**
 * User-visible copy for the Email Settings page. All strings live here so
 * tone/copy edits never touch JSX.
 *
 * Adding a new event type = add the enum on the backend + add a label here
 * + add a backend EVENT_GROUP entry. Two FE places, never more.
 */
export const emailSettingsCopy = {
  title: 'Email settings',
  subtitle: 'Choose which platform emails you want delivered, and to which address.',

  recipientLabel: 'Send emails to',
  recipientHint:
    'Default is your account email. Changing this updates every notification you are subscribed to.',
  changeRecipient: 'Change',

  notificationsHeader: 'Notifications',

  recentSendsHeader: 'Recent activity',
  recentSendsSubtitle: 'The last 7 days of emails sent to you.',
  noActivity: 'No emails in the last 7 days.',

  requiredHint: 'Required by admin',

  recipientOverlayTitle: 'Change notification address',
  recipientOverlaySubtitle:
    'New emails will be delivered here. Existing in-flight sends are unaffected.',
  recipientOverlaySave: 'Save address',
  recipientOverlayCancel: 'Cancel',

  toast: {
    subscriptionUpdated: 'Notification updated.',
    recipientUpdated: 'Notification address updated.',
  },

  error: {
    recipientInvalid: 'Enter a valid email address.',
    recipientDomainBlocked: 'That domain is not allowed for this workspace.',
    subscriptionLocked: 'This notification is required by your admin and cannot be changed.',
    listFailed: 'Could not load your email settings.',
    updateFailed: 'Could not update this notification.',
    recipientFailed: 'Could not update your notification address.',
    recentSendsFailed: 'Could not load recent activity.',
  },

  groups: {
    scheduled_job: 'Scheduled jobs',
    workflow: 'Workflows',
    system: 'System',
  } as Record<string, string>,

  events: {
    'scheduled_job.failed': 'Email me when a scheduled job I own fails',
    'scheduled_job.completed': 'Email me when a scheduled job I own finishes successfully',
    'workflow_run.failed': 'Email me when a workflow run fails',
    'workflow_run.completed': 'Email me when a workflow run finishes successfully',
  } as Record<string, string>,

  columns: {
    sentAt: 'Time',
    subject: 'Subject',
    status: 'Status',
  },

  status: {
    sent: 'Sent',
    failed: 'Failed',
    bounced: 'Bounced',
    not_configured: 'Skipped — mail not configured',
  } as Record<string, string>,
} as const;
